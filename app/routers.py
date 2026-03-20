"""Notification service API routers."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .models import Notification, NotificationPreference, NotificationType, NotificationChannel


router = APIRouter(prefix="/notifications", tags=["notifications"])


# Request/Response models
class NotificationCreate(BaseModel):
    title: str
    message: str
    notification_type: str = "info"
    channel: str = "in_app"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    action_url: Optional[str] = None


class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    notification_type: str
    is_read: bool
    entity_type: Optional[str]
    entity_id: Optional[str]
    action_url: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class NotificationPreferencesUpdate(BaseModel):
    email_agent_created: Optional[bool] = None
    email_workflow_completed: Optional[bool] = None
    email_workflow_failed: Optional[bool] = None
    email_billing_alerts: Optional[bool] = None
    email_system_updates: Optional[bool] = None
    email_marketing: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None


def get_user_id(x_user_id: str = Header(None)) -> UUID:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID required")
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")


@router.get("", response_model=List[NotificationResponse])
async def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """List notifications for the current user."""
    try:
        query = select(Notification).where(Notification.user_id == user_id)
        
        if unread_only:
            query = query.where(Notification.is_read == False)
        
        query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        
        result = await session.execute(query)
        notifications = result.scalars().all()
        
        return [
            NotificationResponse(
                id=str(n.id),
                title=n.title,
                message=n.message,
                notification_type=n.notification_type.value if n.notification_type else "info",
                is_read=n.is_read,
                entity_type=n.entity_type,
                entity_id=str(n.entity_id) if n.entity_id else None,
                action_url=n.action_url,
                created_at=n.created_at.isoformat()
            )
            for n in notifications
        ]
    except Exception:
        # Return empty list if database is unavailable
        return []


@router.get("/unread-count")
async def get_unread_count(
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Get count of unread notifications."""
    result = await session.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user_id)
        .where(Notification.is_read == False)
    )
    count = result.scalar()
    return {"unread_count": count}


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Mark a notification as read."""
    result = await session.execute(
        select(Notification)
        .where(Notification.id == notification_id)
        .where(Notification.user_id == user_id)
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    await session.commit()
    
    return {"status": "read"}


@router.post("/read-all")
async def mark_all_as_read(
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Mark all notifications as read."""
    await session.execute(
        update(Notification)
        .where(Notification.user_id == user_id)
        .where(Notification.is_read == False)
        .values(is_read=True, read_at=datetime.utcnow())
    )
    await session.commit()
    
    return {"status": "all_read"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Delete a notification."""
    result = await session.execute(
        select(Notification)
        .where(Notification.id == notification_id)
        .where(Notification.user_id == user_id)
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    await session.delete(notification)
    await session.commit()
    
    return {"status": "deleted"}


@router.get("/preferences")
async def get_preferences(
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Get notification preferences."""
    result = await session.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    
    if not prefs:
        # Return defaults
        return {
            "email_agent_created": True,
            "email_workflow_completed": True,
            "email_workflow_failed": True,
            "email_billing_alerts": True,
            "email_system_updates": True,
            "email_marketing": False,
            "in_app_enabled": True,
            "push_enabled": False,
        }
    
    return {
        "email_agent_created": prefs.email_agent_created,
        "email_workflow_completed": prefs.email_workflow_completed,
        "email_workflow_failed": prefs.email_workflow_failed,
        "email_billing_alerts": prefs.email_billing_alerts,
        "email_system_updates": prefs.email_system_updates,
        "email_marketing": prefs.email_marketing,
        "in_app_enabled": prefs.in_app_enabled,
        "push_enabled": prefs.push_enabled,
    }


@router.put("/preferences")
async def update_preferences(
    updates: NotificationPreferencesUpdate,
    user_id: UUID = Depends(get_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Update notification preferences."""
    result = await session.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    
    if not prefs:
        prefs = NotificationPreference(user_id=user_id)
        session.add(prefs)
    
    # Update only provided fields
    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prefs, key, value)
    
    await session.commit()
    
    return {"status": "updated"}


# Internal endpoint for creating notifications
@router.post("/internal/create")
async def create_notification(
    notification: NotificationCreate,
    target_user_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Create a notification (internal use)."""
    try:
        target_user_uuid = UUID(target_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid target_user_id")

    notif = Notification(
        user_id=target_user_uuid,
        title=notification.title,
        message=notification.message,
        notification_type=NotificationType(notification.notification_type),
        channel=NotificationChannel(notification.channel),
        entity_type=notification.entity_type,
        entity_id=notification.entity_id,
        action_url=notification.action_url,
    )
    session.add(notif)
    await session.commit()
    await session.refresh(notif)
    
    return {"id": str(notif.id), "status": "created"}


@router.get("/health")
async def health():
    return {"status": "ok", "service": "notifications"}
