# In netlify/functions/api.py

import sys
import os
from serverless_wsgi import handle

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from src.app import app

def handler(event, context):
    """
    This is the main entry point for the Netlify Function.
    It uses serverless-wsgi to translate the AWS Lambda event
    into a WSGI request that Flask can understand.
    """
    return handle(app, event, context)