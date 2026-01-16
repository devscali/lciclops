"""
Firebase Service - Little Caesars Reports
Aurelia: "Toda la interacción con Firebase pasa por aquí"
"""
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize Firebase
_firebase_app = None


def init_firebase():
    """Inicializa Firebase Admin SDK"""
    global _firebase_app
    if _firebase_app is None:
        try:
            cred = credentials.Certificate(settings.firebase_credentials_path)
            _firebase_app = firebase_admin.initialize_app(cred, {
                'storageBucket': settings.gcs_bucket
            })
            logger.info("Firebase initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    return _firebase_app


def get_firestore_client():
    """Obtiene cliente de Firestore"""
    init_firebase()
    return firestore.client()


def get_storage_bucket():
    """Obtiene bucket de Cloud Storage"""
    init_firebase()
    return storage.bucket()


class FirebaseService:
    """
    Aurelia: "Clase principal para interactuar con Firebase"
    """

    def __init__(self):
        self.db = get_firestore_client()
        self.bucket = get_storage_bucket()

    # === Auth Methods ===
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verifica un token de Firebase Auth"""
        try:
            decoded_token = auth.verify_id_token(token)
            return decoded_token
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None

    async def get_user_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        """Obtiene usuario de Firebase Auth"""
        try:
            user = auth.get_user(uid)
            return {
                "uid": user.uid,
                "email": user.email,
                "display_name": user.display_name,
                "email_verified": user.email_verified,
            }
        except Exception as e:
            logger.error(f"Failed to get user {uid}: {e}")
            return None

    async def set_custom_claims(self, uid: str, claims: Dict[str, Any]):
        """Establece custom claims (roles) para un usuario"""
        try:
            auth.set_custom_user_claims(uid, claims)
            logger.info(f"Custom claims set for user {uid}")
        except Exception as e:
            logger.error(f"Failed to set custom claims: {e}")
            raise

    # === Firestore Methods ===
    async def create_document(
        self,
        collection: str,
        data: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> str:
        """Crea un documento en Firestore"""
        try:
            data["created_at"] = datetime.utcnow()
            data["updated_at"] = datetime.utcnow()

            if doc_id:
                self.db.collection(collection).document(doc_id).set(data)
                return doc_id
            else:
                doc_ref = self.db.collection(collection).add(data)
                return doc_ref[1].id
        except Exception as e:
            logger.error(f"Failed to create document in {collection}: {e}")
            raise

    async def get_document(
        self,
        collection: str,
        doc_id: str
    ) -> Optional[Dict[str, Any]]:
        """Obtiene un documento de Firestore"""
        try:
            doc = self.db.collection(collection).document(doc_id).get()
            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            raise

    async def update_document(
        self,
        collection: str,
        doc_id: str,
        data: Dict[str, Any]
    ):
        """Actualiza un documento en Firestore"""
        try:
            data["updated_at"] = datetime.utcnow()
            self.db.collection(collection).document(doc_id).update(data)
        except Exception as e:
            logger.error(f"Failed to update document {doc_id}: {e}")
            raise

    async def delete_document(self, collection: str, doc_id: str):
        """Elimina un documento de Firestore"""
        try:
            self.db.collection(collection).document(doc_id).delete()
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            raise

    async def query_documents(
        self,
        collection: str,
        filters: List[tuple] = None,
        order_by: str = None,
        order_direction: str = "DESCENDING",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query documents with filters
        filters: List of tuples (field, operator, value)
        """
        try:
            query = self.db.collection(collection)

            if filters:
                for field, operator, value in filters:
                    query = query.where(field, operator, value)

            if order_by:
                direction = (
                    firestore.Query.DESCENDING
                    if order_direction == "DESCENDING"
                    else firestore.Query.ASCENDING
                )
                query = query.order_by(order_by, direction=direction)

            query = query.limit(limit)

            docs = query.stream()
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                results.append(data)

            return results
        except Exception as e:
            logger.error(f"Failed to query {collection}: {e}")
            raise

    # === Storage Methods ===
    async def upload_file(
        self,
        file_content: bytes,
        destination_path: str,
        content_type: str = "application/pdf"
    ) -> str:
        """Sube un archivo a Cloud Storage"""
        try:
            blob = self.bucket.blob(destination_path)
            blob.upload_from_string(file_content, content_type=content_type)
            blob.make_public()  # O usar signed URLs para más seguridad
            return blob.public_url
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise

    async def download_file(self, file_path: str) -> bytes:
        """Descarga un archivo de Cloud Storage"""
        try:
            blob = self.bucket.blob(file_path)
            return blob.download_as_bytes()
        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            raise

    async def delete_file(self, file_path: str):
        """Elimina un archivo de Cloud Storage"""
        try:
            blob = self.bucket.blob(file_path)
            blob.delete()
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            raise

    async def get_signed_url(self, file_path: str, expiration: int = 3600) -> str:
        """Genera URL firmada para acceso temporal"""
        from datetime import timedelta
        try:
            blob = self.bucket.blob(file_path)
            url = blob.generate_signed_url(
                expiration=timedelta(seconds=expiration),
                method="GET"
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate signed URL: {e}")
            raise


# Singleton instance
_firebase_service: Optional[FirebaseService] = None


def get_firebase_service() -> FirebaseService:
    global _firebase_service
    if _firebase_service is None:
        _firebase_service = FirebaseService()
    return _firebase_service
