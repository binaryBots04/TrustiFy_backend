from flask import Flask, Response, jsonify, Blueprint, request
from PIL import Image
import pytesseract
import re
import io
import requests
import torch
from datetime import datetime
import torch.nn.functional as F
from pymongo import MongoClient
from flask_pymongo import PyMongo 
import torch.nn as nn
from torchvision import models, transforms
from fuzzywuzzy import fuzz
import cv2
import numpy as np
import json

verify_bp = Blueprint('verify_bp', __name__)

with open('sample_db.json', 'r') as f:
    sample_db = json.load(f)

PINATA_API_KEY = '04b26ee360171f03ae2b'
PINATA_SECRET_API_KEY = '250fe3ce90862d18f94ced6c065a6bec5a956d528aef8ab9d737a9b3f0ca8065'

def download_image_from_ipfs(ipfs_link):
    ipfs_gateway = "https://ipfs.io/ipfs/"
    ipfs_hash = ipfs_link.split("ipfs://")[-1]
    download_url = ipfs_gateway + ipfs_hash
    response = requests.get(download_url)
    if response.status_code == 200:
        return Image.open(io.BytesIO(response.content))
    else:
        raise Exception("Failed to download image from IPFS")

def upload_to_ipfs(image_data):
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_SECRET_API_KEY
    }
    files = {
        'file': ('image.jpg', io.BytesIO(image_data), 'image/jpeg')
    }
    response = requests.post(url, files=files, headers=headers)
    if response.status_code == 200:
        ipfs_hash = response.json()["IpfsHash"]
        return ipfs_hash
    else:
        raise Exception("Failed to upload to IPFS: " + response.text)

@verify_bp.route('/p', methods=['POST'])
def process_image_ipfs():
    print("Route /process-ipfs was hit")
    data = request.get_json()
    
    if not data or 'ipfs_link' not in data:
        return jsonify({"error": "No IPFS link provided"}), 400

    ipfs_link = data['ipfs_link']
    
    try:
        image = download_image_from_ipfs(ipfs_link)
        return process_image(image)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def process_image(image):
    extracted_text = pytesseract.image_to_string(image).lower()

    print(extracted_text)

    name_pattern = r'name\s*:\s*[_\W]*([a-z\s]+)'
    roll_number_pattern = r'roll\s*no\s*:\s*(\d{8})'
    result_pattern = r'result\s*:\s*(\w+)'
    cpi_pattern = r'cpi\s*:\s*([\d.]+)'
    
    name = re.search(name_pattern, extracted_text).group(1).strip() if re.search(name_pattern, extracted_text) else "not found"
    roll_number = re.search(roll_number_pattern, extracted_text).group(1).strip() if re.search(roll_number_pattern, extracted_text) else "not found"
    result = re.search(result_pattern, extracted_text).group(1).strip() if re.search(result_pattern, extracted_text) else "not found"
    cpi = re.search(cpi_pattern, extracted_text).group(1).strip() if re.search(cpi_pattern, extracted_text) else "not found"

    extracted_data = {"Name": name, "Roll Number": roll_number, "Result": result, "CPI": cpi}

    print(extracted_data)

    db_entry = next((entry for entry in sample_db if entry["Roll Number"] == roll_number), None)

    if db_entry:
        name_match_score = fuzz.partial_ratio(name, db_entry["Name"])
        result_match_score = fuzz.partial_ratio(result, db_entry["Result"])
        cpi_match_score = fuzz.partial_ratio(cpi, db_entry["CPI"])

        fuzzy_results = {
            "Name Match Score": name_match_score,
            "Result Match Score": result_match_score,
            "CPI Match Score": cpi_match_score
        }

        print(fuzzy_results)

        if any(score < 85 for score in fuzzy_results.values()):
            return jsonify({"Match Result": 0}), 200  
        
        return jsonify({"Match Result": 1}), 200 
    
    return jsonify({"error": "Roll Number not found in database"}), 404