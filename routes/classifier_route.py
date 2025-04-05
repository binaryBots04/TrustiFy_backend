from flask import Flask, Response, jsonify, Blueprint, request
from PIL import Image
import io
import requests
import torch
from datetime import datetime
import torch.nn.functional as F
import torch.nn as nn
from torchvision import models, transforms
import cv2
import numpy as np
import json
from model.model_classify import ResumeDocument

classify_bp = Blueprint('classify_bp', __name__)

class_names = ['admit', 'college_id', 'result']

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

model = models.efficientnet_b0(pretrained=True)
num_ftrs = model.classifier[1].in_features
model.classifier[1] = nn.Linear(num_ftrs, len(class_names)) 
model.load_state_dict(torch.load('./ml/document_classifier.pth')) 
model = model.to(device)
model.eval()

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

def classify_document(image):
    preprocess = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    img_tensor = preprocess(image).unsqueeze(0).to(device)

    with torch.no_grad():
        output = model(img_tensor)
        probs = F.softmax(output, dim=1)
        
        max_prob, pred_idx = torch.max(probs, dim=1)

    if max_prob.item() < 0.80: 
        return 'Other'  
        
    return class_names[pred_idx.item()]  

@classify_bp.route('/c/<auth_id>', methods=['GET', 'POST'])
def classify_ipfs(auth_id):  
    if request.method == 'POST':
        data = request.get_json()
        if not data or 'ipfs_link' not in data:
            return jsonify({"error": "No IPFS link provided"}), 400

        ipfs_link = data['ipfs_link']
        
        try:
            image = download_image_from_ipfs(ipfs_link)
            predicted_class = classify_document(image)

            if predicted_class:
    
                ResumeDocument.create(authid=auth_id, ipfs_hash=ipfs_link, doctype=predicted_class)

            return jsonify({"predicted_document_type": predicted_class}), 200
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'GET':
        try:
            documents = ResumeDocument.get_by_authid(auth_id)
            return jsonify(documents if documents else []), 200
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
