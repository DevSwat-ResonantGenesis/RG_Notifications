"""Notification models."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
import enum

Base = declarative_base()


class NotificationType(str, enum.Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SYSTEM = "system"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    PUSH = "push"


class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(SQLEnum(NotificationType), default=NotificationType.INFO)
    channel = Column(SQLEnum(NotificationChannel), default=NotificationChannel.IN_APP)
    
    # Link to related entity
    entity_type = Column(String(50))  # agent, workflow, task, etc.
    entity_id = Column(UUID(as_uuid=True))
    action_url = Column(String(500))
    
    # Status
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime)
    
    # Metadata
    extra_metadata = Column(Text)  # JSON string
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    
    # Email preferences
    email_agent_created = Column(Boolean, default=True)
    email_workflow_completed = Column(Boolean, default=True)
    email_workflow_failed = Column(Boolean, default=True)
    email_billing_alerts = Column(Boolean, default=True)
    email_system_updates = Column(Boolean, default=True)
    email_marketing = Column(Boolean, default=False)
    
    # In-app preferences
    in_app_enabled = Column(Boolean, default=True)
    
    # Push preferences
    push_enabled = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
