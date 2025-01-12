from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from controllers.detectron2 import router as detectron2_router
from controllers.chatLogProcessing import router as chatlog_upload_router


app = FastAPI()
'''
Access the API documentation at:

Swagger UI: http://127.0.0.1:8000/docs
Redoc UI: http://127.0.0.1:8000/redoc
'''

# Add CORS middleware
origins = [
  "http://localhost:3000",  # Local development frontend (e.g., React, Vue)
  "https://yourfrontenddomain.com",  # Production frontend
]

app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

# tag parameter helps group the routes for better documentation in the Swagger UI
app.include_router(detectron2_router, prefix="/api", tags=["detectron2"])
app.include_router(chatlog_upload_router, prefix="/api", tags=["chatlog_upload"])

@app.get("/")
def read_root():
  return {"message": "Hello, World!"}
