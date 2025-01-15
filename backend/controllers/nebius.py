import os
import traceback
from openai import OpenAI
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from dotenv import load_dotenv
import json
from utils.pinecone_db import generate_query_embedding, search_in_pinecone
from .chatLogProcessing import chatlog_from_chatid

load_dotenv()

# Initialize the FastAPI router
router = APIRouter()

# Initialize the Nebius API client
client = OpenAI(
  base_url="https://api.studio.nebius.ai/v1/",
  api_key=os.environ.get("NEBIUS_API_KEY")  # Ensure your API key is set in the environment
)

@router.post("/nebius-chat")
async def nebius_chat(data: dict):
  prompt = data.get('prompt')
  user_id = data.get('user_id')
  message_from_frontend = data.get('messages')
  searchChat = data.get('searchChat')
  searchImage = data.get('searchImage')

  if not prompt:
    raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
  try:
    key_item = extract_key_item_from_prompt(prompt)
    key_item_embedding = generate_query_embedding(key_item)
    

    # only being used in final_response
    pc_chat_response = None
    pc_image_response = None
    if(searchChat):
      pc_chat_response = search_in_pinecone(key_item_embedding, user_id, "message", 3)

    if(searchImage):
      pc_image_response = search_in_pinecone(key_item_embedding, user_id, "image", 2)
    
    print(pc_image_response)
    print(pc_chat_response)
  
    formatted_messages = [
      {"role": "user" if msg["sender"] == "user" else "assistant", "content": msg["text"]}
      for msg in message_from_frontend 
    ]
    
    formatted_messages = formatted_messages[-5:] if len(formatted_messages) > 5 else formatted_messages

    completion = None

    if(pc_chat_response and pc_image_response):
      completion = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages = [{
            "role": "system",
            "content": '''Your goal is to act as an AI chat bot to help people who have lost there home remember items lost in there home. 
            We may or may not provide you with information. If the user is vague try to help them jog there memory. 
            If you receive items such as chat logs or images let the user know. ENSURE TO ACT AS IF YOU ARE TALKING TO SOMEONE SO HAVE SOME BREVITY AT TIMES.'''

            # make sure to make it talk like an ai aswell -> if i say hello it should talk to me normally like an assistant
          },
          *formatted_messages,
          {
            "role": "user",
            "content": f'''Here are some related messages and detected items in the images related to the user message. Ensure to let the user know about this:
            {', '.join(["image" + str(i) + " items: " + str(pc_image_response[i]['items']) for i in range(len(pc_image_response))])}
            Messages: {', '.join(["Found " + str(pc_chat_response[i]['item']) + " in " + str(pc_chat_response[i]['message']) for i in range(len(pc_chat_response))])},
            User message: {prompt}'''
          }
        ],
        temperature=0.6,
        max_tokens=512,
        top_p=0.9
      )
    elif pc_chat_response:
      completion = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages = [{
            "role": "system",
            "content": '''Your goal is to act as an AI chat bot to help people who have lost there home remember items lost in there home. 
            We may or may not provide you with information. If the user is vague try to help them jog there memory. 
            If you receive items such as chat logs or images let the user know. ENSURE TO ACT AS IF YOU ARE TALKING TO SOMEONE SO HAVE SOME BREVITY AT TIMES.'''

            # make sure to make it talk like an ai aswell -> if i say hello it should talk to me normally like an assistant
          },
          *formatted_messages,
          {
            "role": "user",
            "content": f'''Here are some related messages to the user query, ENSURE TO LET THE USER KNOW ABOUT THE FOUND MESSAGE it will be visible to them in the UI just need to bring it up in conversation. ENSURE YOU RESPOND AS IF YOU ARE STILL TALKING: 
            messages: {["Found " + pc_chat_response[i]['item'] + "in " + pc_chat_response[i]['message'] for i in range(len(pc_chat_response))]}, 
            user message: {prompt}'''
          }
        ],
        temperature=0.6,
        max_tokens=512,
        top_p=0.9
      )
    elif pc_image_response:
      completion = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages = [{
            "role": "system",
            "content": '''Your goal is to act as an AI chat bot to help people who have lost there home remember items lost in there home. 
            We may or may not provide you with information. If the user is vague try to help them jog there memory. 
            If you receive items such as chat logs or images let the user know. ENSURE TO ACT AS IF YOU ARE TALKING TO SOMEONE SO HAVE SOME BREVITY AT TIMES.'''

            # make sure to make it talk like an ai aswell -> if i say hello it should talk to me normally like an assistant
          },
          *formatted_messages,
          {
            "role": "user",
            "content": f'''Here are some items found in images that are related to the user query, ENSURE TO LET THE USER KNOW ABOUT THE FOUND IMAGES it will be visible to them in the UI you just need to bring it up  in conversation. ENSURE YOU RESPOND AS IF YOU ARE STILL TALKING TO THEM: 
            {', '.join([f"image{str(i)} items found: {str(pc_image_response[i]['items'])}" for i in range(len(pc_image_response))])},
            user message: {prompt}'''
          }
        ],
        temperature=0.6,
        max_tokens=512,
        top_p=0.9
      )
    else:
      completion = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages = [{
            "role": "system",
            "content": '''Your goal is to act as an AI chat bot to help people who have lost there home remember items lost in there home. 
            We may or may not provide you with information. If the user is vague try to help them jog there memory. 
            If you receive items such as chat logs or images let the user know. ENSURE TO ACT AS IF YOU ARE TALKING TO SOMEONE SO HAVE SOME BREVITY AT TIMES.'''

            # make sure to make it talk like an ai aswell -> if i say hello it should talk to me normally like an assistant
          },
          *formatted_messages,
          {
            "role": "user",
            "content": f'''
            No messages or images searched JUST RESPOND TO USER PROMPT,
            user message: {prompt}'''
          }
        ],
        temperature=0.6,
        max_tokens=512,
        top_p=0.9
      )

    # Return the completion response
    response = json.loads(completion.to_json())

    final_response = {
      "response": response,
      "pc_chat_response": pc_chat_response,
      "pc_image_response": pc_image_response
    }

    # return {"response": response}
    return final_response
    

  except Exception as e:
    print(e)
    raise HTTPException(status_code=500, detail=f"Error calling Nebius API: {str(e)}")


def extract_key_item_from_prompt(prompt: str):
  completion = client.chat.completions.create(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct-fast",
    messages=[
      {
        "role": "system",
        "content": '''You are an assistant that extracts a specific key item and context of what 
        the user is looking for filling insurance claims.
        '''
      },
      {
        "role": "user",
        "content": f"Extract a key item of what I'm looking for from my prompt:\n{prompt}\n\nFormat as:\n* Item: [item] Context: [context]. "
        # if you believe there is no query, return no query
        # if its a generic query, make up query "like I need to find some items"
      }
    ],
    temperature=0
  )
  
  response = json.loads(completion.to_json())
  key_item = response['choices'][0]['message']['content'].split('*')

  return key_item[1] if len(key_item) > 1 else key_item[0]
