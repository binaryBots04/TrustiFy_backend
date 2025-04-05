from flask import Flask
from config import Config
from db import mongo
from routes.classifier_route import classify_bp
# from routes.resume_route import resume_bp
from routes.verify_route import verify_bp
from routes.overlay_route import overlay_bp
from flask_cors import CORS

app = Flask(__name__)
app.config.from_object(Config)
mongo.init_app(app)

CORS(app)

app.register_blueprint(classify_bp)
# app.register_blueprint(resume_bp)
app.register_blueprint(verify_bp)
app.register_blueprint(overlay_bp)

if __name__ == '__main__':
    app.run(debug=True)
