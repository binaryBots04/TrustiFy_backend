from flask import Flask, Response, jsonify, Blueprint, request
from PIL import Image
import io
import requests
import torch.nn.functional as F
from pymongo import MongoClient
from flask_pymongo import PyMongo 
from fuzzywuzzy import fuzz
import cv2
import numpy as np
import json
from model.model_classify import ResumeDocument

overlay_bp = Blueprint("overlay_bp", __name__)

PINATA_API_KEY = '04b26ee360171f03ae2b'
PINATA_SECRET_API_KEY = '250fe3ce90862d18f94ced6c065a6bec5a956d528aef8ab9d737a9b3f0ca8065'

SIGNATURE_POSITION = [300, 500]
SIGNATURE_SIZE = (200, 200) 

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
    

def overlay_signature(background_image, signature_path, position):
    signature = cv2.imread(signature_path, cv2.IMREAD_UNCHANGED)

    if signature is None:
        raise FileNotFoundError(f"Signature image at path {signature_path} could not be loaded.")

    signature = cv2.resize(signature, SIGNATURE_SIZE, interpolation=cv2.INTER_AREA)

    signature_height, signature_width = signature.shape[:2]
    x, y = position

    if (y < 0) or (x < 0) or (y + signature_height > background_image.shape[0]) or (x + signature_width > background_image.shape[1]):
        raise ValueError("Signature image does not fit in the background image at the specified position.")

    if signature.shape[2] == 4: 
        b, g, r, a = cv2.split(signature)
        overlay = cv2.merge((b, g, r))
        mask = a
        
        for c in range(0, 3):
            background_image[y:y + signature_height, x:x + signature_width, c] = \
                (overlay[..., c] * (mask / 255.0) + 
                 background_image[y:y + signature_height, x:x + signature_width, c] * (1.0 - mask / 255.0))
    else: 
        background_image[y:y + signature_height, x:x + signature_width] = signature

    success, buffer = cv2.imencode('.jpg', background_image)
    if not success:
        raise Exception("Failed to encode image")

    return buffer.tobytes()


@overlay_bp.route('/o', methods=['POST'])
def overlay_signature_endpoint():
    try:
        data = request.get_json()
        if not data or 'ipfs_link' not in data:
            return jsonify({"status": "error", "message": "No IPFS link provided"}), 400

        background_ipfs_link = data['ipfs_link']
        signature_path = 'sign2.png'  

        background_image_pil = download_image_from_ipfs(background_ipfs_link)
        background_image_cv = cv2.cvtColor(np.array(background_image_pil), cv2.COLOR_RGB2BGR)

        image_data = overlay_signature(background_image_cv, signature_path, SIGNATURE_POSITION)

        new_ipfs_hash = upload_to_ipfs(image_data)

        updated_doc = ResumeDocument.update_by_ipfs_hash(
            old_ipfs_hash=background_ipfs_link,
            new_ipfs_hash=new_ipfs_hash,
            verify_flag=True
        )

        return jsonify({
            "status": "success",
            "ipfs_hash": new_ipfs_hash,
            "updated_doc": updated_doc
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

