import json
from fastapi import HTTPException
from openai import OpenAI
from sentence_transformers import SentenceTransformer
import torch
from transformers import CLIPModel, CLIPProcessor
import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

# Initialize Nebius OpenAI client
client = OpenAI(
    base_url="https://api.studio.nebius.ai/v1/",
    api_key=os.environ.get("NEBIUS_API_KEY")
)

# Initialize CLIP for text embeddings
clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")


# Initialize Pinecone
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))

# Define index name
index_name = "item-context-embeddings-512"

# Create the index if it doesn't exist
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=512,
        spec=ServerlessSpec(
            cloud="aws",  # Specify your cloud provider
            region="us-east-1"  # Specify your region
        ),
        metric="cosine"  # You can use 'cosine', 'euclidean', or 'dotproduct'
    )

# Connect to the index
index = pc.Index(index_name)

# Query the index to check the inserted vectors
result = index.describe_index_stats()
print('inserted vectors: ', result)

def clear_index():
    """
    Clears all vectors from the Pinecone index without deleting the index.
    """
    try:
        index.delete(delete_all=True)
    except Exception as e:
        print(f"Error clearing the index '{index_name}': {e}")

# clear_index() 

# this dont work
def query_index(query_vector):
    index_stats = index.describe_index_stats()
    print('W: ', index_stats['total_vector_count'])
    '''
    query_vector = query_vector.tolist()
    response = index.query(query_vector=query_vector, top_k=1)
    '''
    response = index.query(query_vector=query_vector, top_k=1)

    index_stats =  index.describe_index_stats()
    print('W? ', index_stats['total_vector_count'])
    return response


def extract_insights_from_chatlog(chatlog_content):
    completion = client.chat.completions.create(
        model="meta-llama/Meta-Llama-3.1-8B-Instruct-fast",
        messages=[
            {
                "role": "system",
                "content": "You are an assistant that extracts key items, the location of the item, and the message (including timestamp) they come from in chat logs."
            },
            {
                "role": "user",
                "content": f"Extract key items, contexts, and messages from this chat log:\n{chatlog_content}\n\nFormat as:\n* Item: [item]\n* Context: [context]\n* Message: [Original Message]"
            }
        ],
        temperature=0
    )
    
    # Parse the response
    response = json.loads(completion.to_json())
    content = response['choices'][0]['message']['content'].split('*')

    items = []
    context = []
    messages = []

    for i in range(1, len(content) - 2, 3):
        items.append(content[i].strip())
        context.append(content[i+1].strip())
        messages.append(content[i+2].strip())
    
    dict_item_context = {
        "ids": [],
        "items": items,
        "context": context,
        "messages": messages
    }

    return dict_item_context

def generate_embeddings(dict_item_context):
    """
    Generates embeddings for a list of insights using CLIP.

    Args:
        insights (list of str): The extracted insights or key phrases.

    Returns:
        list of numpy.ndarray: Embeddings for each insight.
    """
    # Prepare text input for CLIP (item + context)
    texts = [item + ' ' + context for item, context in zip(dict_item_context["items"], dict_item_context["context"])]
    
    # Process the text using CLIPProcessor
    inputs = clip_processor(text=texts, return_tensors="pt", padding=True, truncation=True)
    
    # Generate text embeddings using CLIPModel
    with torch.no_grad():
        text_embeddings = clip_model.get_text_features(**inputs)

    return text_embeddings


# With the extracted key item from the user prompt, we pass it here to make it a query embedding
def generate_query_embedding(key_item):
    if not key_item:
        raise HTTPException(status_code=400, detail="Key item is empty.")
    
    inputs = clip_processor(text=[key_item], return_tensors="pt", padding=True, truncation=True)

    with torch.no_grad():
        query_embedding = clip_model.get_text_features(**inputs)

    return query_embedding


def store_embeddings_in_pinecone(dict_item_context, embeddings, chat_id, file, user_id, image_id, type):
    """
    Stores embeddings in Pinecone with metadata.

    Args:
        dict_item_context (dict): Dictionary containing "items" and "context".
        embeddings (list): List of embeddings corresponding to each item-context pair.
        filename (str): Name of the uploaded file (used as a unique identifier).
    """

    print(file)
    if (type=="message"):
        pinecone_data = [
            {
                "id": file + '_' + str(dict_item_context["ids"][i]),
                "values": embedding.tolist(),  # Convert NumPy array to list
                "metadata": {
                    "chat_id": chat_id,
                    "message_id": dict_item_context["ids"][i],
                    "type": type,
                    "item": dict_item_context["items"][i],
                    "context": dict_item_context["context"][i],
                    "message": dict_item_context["messages"][i],
                    "user_id": user_id
                }
            }
            for i, embedding in enumerate(embeddings)
        ]
    else:
        pinecone_data = [
            {
                "id": file + '_' + str(image_id),
                "values": embeddings[0].tolist(),  # Convert NumPy array to list
                "metadata": {
                    "type": type,
                    "image_id": image_id,
                    "user_id": user_id,
                    "items": dict_item_context["items"],
                    "filename": file,
                }
            }
        ]

    # Upsert data into Pinecone
    try:
        index.upsert(vectors=pinecone_data)
        return pinecone_data
    except Exception as e:
        print(f"Error upserting data to Pinecone: {e}")
        raise

def search_in_pinecone(query_embedding, user_id, type, top_k):
    
    # Step 1: Query Pinecone to get the top 5 closest results
    query_vector = query_embedding.cpu().numpy().tolist()
    result = index.query(
        vector=query_vector, 
        top_k=top_k, 
        include_metadata=True,  # You can retrieve metadata too
        metric="cosine",
        filter={"user_id": user_id, "type": type}
    )
    
    # Step 2: Parse and return results
    results = []
    
    for match in result['matches']:
        # Each match includes metadata (item, context, etc.)
        item_metadata = match['metadata']
        results.append(item_metadata)

    return results
