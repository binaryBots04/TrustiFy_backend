from db import mongo
from datetime import datetime
from bson.objectid import ObjectId

class ResumeDocument:
    @staticmethod
    def create(authid, ipfs_hash, doctype):
        document = {
            "authid": authid,
            "ipfs_hash": ipfs_hash,
            "upload_time": datetime.utcnow(),
            "doctype": doctype,
            "verify_flag": False
        }
        mongo.db.resume_documents.insert_one(document)
        return ResumeDocument.serialize(document)

    @staticmethod
    def get_by_authid(authid):
        docs = list(mongo.db.resume_documents.find({"authid": authid}))
        return [ResumeDocument.serialize(doc) for doc in docs]

    @staticmethod
    def update(authid, data):
        mongo.db.resume_documents.update_many({"authid": authid}, {"$set": data})
        return ResumeDocument.get_by_authid(authid)

    @staticmethod
    def delete(authid):
        return mongo.db.resume_documents.delete_many({"authid": authid})

    @staticmethod
    def update_by_ipfs_hash(old_ipfs_hash, new_ipfs_hash, verify_flag):
        mongo.db.resume_documents.update_one(
            {"ipfs_hash": old_ipfs_hash},
            {"$set": {
                "ipfs_hash": new_ipfs_hash,
                "verify_flag": verify_flag
            }}
        )
        updated_doc = mongo.db.resume_documents.find_one({"ipfs_hash": new_ipfs_hash})
        return ResumeDocument.serialize(updated_doc)

    @staticmethod
    def serialize(doc):
        if doc is not None:
            doc["_id"] = str(doc["_id"])
        return doc
