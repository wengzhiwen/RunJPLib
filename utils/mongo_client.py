import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import logging

def get_mongo_client():
    """
    Establishes a connection to MongoDB using credentials from environment variables.
    """
    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        logging.error("MONGODB_URI environment variable not set.")
        return None

    try:
        # Create a new client and connect to the server
        client = MongoClient(mongo_uri, server_api=ServerApi('1'))
        # Send a ping to confirm a successful connection
        client.admin.command('ping')
        logging.info("Pinged your deployment. You successfully connected to MongoDB!")
        return client
    except Exception as e:
        logging.error(f"Error connecting to MongoDB: {e}")
        return None

# You can also initialize a global client instance if you prefer
# client = get_mongo_client()
# db = client.get_database("RunJPLib") if client else None
