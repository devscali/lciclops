"""
Auth Router - Little Caesars Reports
Aurelia: "Endpoints de autenticación, todo pasa por Firebase Auth"
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Optional

from app.models import UserCreate, UserResponse, UserUpdate, UserRole
from app.services import get_firebase_service, FirebaseService

router = APIRouter(prefix="/auth", tags=["Authentication"])


async def get_current_user(
    authorization: str = Header(...),
    firebase: FirebaseService = Depends(get_firebase_service)
) -> dict:
    """
    Aurelia: "Middleware para verificar el token de Firebase"
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header"
        )

    token = authorization.split(" ")[1]
    user_data = await firebase.verify_token(token)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Obtener datos adicionales del usuario de Firestore
    user_doc = await firebase.get_document("users", user_data["uid"])
    if user_doc:
        user_data.update(user_doc)

    return user_data


@router.post("/register", response_model=UserResponse)
async def register_user(
    user_data: UserCreate,
    firebase: FirebaseService = Depends(get_firebase_service)
):
    """
    Registrar nuevo usuario
    Livia: "Aquí se crean las cuentas nuevas"
    """
    try:
        # Crear documento en Firestore
        user_doc = {
            "email": user_data.email,
            "display_name": user_data.display_name,
            "role": UserRole.USER.value,
            "franchise_id": user_data.franchise_id,
            "preferences": {
                "currency": "MXN",
                "date_format": "DD/MM/YYYY",
                "default_report_type": "pnl"
            }
        }

        # El ID será el UID de Firebase Auth (se debe crear el usuario en el frontend)
        # Este endpoint solo crea el documento en Firestore

        return {
            "id": "pending_firebase_uid",
            "email": user_data.email,
            "display_name": user_data.display_name,
            "role": UserRole.USER,
            "franchise_id": user_data.franchise_id,
            "preferences": user_doc["preferences"]
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/setup-profile")
async def setup_user_profile(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_user),
    firebase: FirebaseService = Depends(get_firebase_service)
):
    """
    Configurar perfil después de registro en Firebase Auth
    Aurelia: "Se llama después de que el usuario se autentica por primera vez"
    """
    try:
        user_doc = {
            "email": current_user["email"],
            "display_name": user_data.display_name,
            "role": UserRole.USER.value,
            "franchise_id": user_data.franchise_id,
            "preferences": {
                "currency": "MXN",
                "date_format": "DD/MM/YYYY",
                "default_report_type": "pnl"
            }
        }

        await firebase.create_document("users", user_doc, doc_id=current_user["uid"])

        return {"message": "Profile created successfully", "user_id": current_user["uid"]}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user)
):
    """
    Obtener perfil del usuario actual
    """
    return {
        "id": current_user.get("uid") or current_user.get("id"),
        "email": current_user.get("email"),
        "display_name": current_user.get("display_name", ""),
        "role": current_user.get("role", UserRole.USER),
        "franchise_id": current_user.get("franchise_id"),
        "preferences": current_user.get("preferences", {
            "currency": "MXN",
            "date_format": "DD/MM/YYYY",
            "default_report_type": "pnl"
        })
    }


@router.put("/profile")
async def update_profile(
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
    firebase: FirebaseService = Depends(get_firebase_service)
):
    """
    Actualizar perfil del usuario
    """
    try:
        update_dict = update_data.model_dump(exclude_none=True)

        if update_dict:
            await firebase.update_document(
                "users",
                current_user["uid"],
                update_dict
            )

        return {"message": "Profile updated successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/set-role")
async def set_user_role(
    user_id: str,
    role: UserRole,
    current_user: dict = Depends(get_current_user),
    firebase: FirebaseService = Depends(get_firebase_service)
):
    """
    Asignar rol a un usuario (solo admin)
    Aurelia: "Solo los admins pueden cambiar roles"
    """
    # Verificar que el usuario actual es admin
    if current_user.get("role") != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can change user roles"
        )

    try:
        # Actualizar custom claims en Firebase Auth
        await firebase.set_custom_claims(user_id, {"role": role.value})

        # Actualizar documento en Firestore
        await firebase.update_document("users", user_id, {"role": role.value})

        return {"message": f"Role updated to {role.value}"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
