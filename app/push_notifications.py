"""
PUSH NOTIFICATION SERVICE
=========================

Multi-provider push notifications for Resonant Genesis.
Supports: Firebase Cloud Messaging (FCM), Apple Push Notifications (APNS), Web Push.

Usage:
    from notification_service.app.push_notifications import get_push_service
    
    push = get_push_service()
    await push.send(user_id="123", title="Alert", body="New message")
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PushProvider(Enum):
    FCM = "fcm"
    APNS = "apns"
    WEB_PUSH = "web_push"


class NotificationPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass
class PushNotification:
    """Push notification payload."""
    title: str
    body: str
    data: Dict[str, Any] = field(default_factory=dict)
    image_url: Optional[str] = None
    icon: Optional[str] = None
    badge: Optional[int] = None
    sound: Optional[str] = None
    priority: NotificationPriority = NotificationPriority.NORMAL
    ttl: int = 86400  # 24 hours
    collapse_key: Optional[str] = None
    channel_id: Optional[str] = None  # Android notification channel
    category: Optional[str] = None  # iOS notification category


@dataclass
class DeviceToken:
    """Device token for push notifications."""
    token: str
    provider: PushProvider
    user_id: str
    device_id: Optional[str] = None
    platform: Optional[str] = None  # ios, android, web
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PushResult:
    """Result of push notification delivery."""
    success: bool
    provider: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    token: Optional[str] = None


# ============== PROVIDERS ==============

class PushProviderBase(ABC):
    """Base class for push notification providers."""
    
    @abstractmethod
    async def send(self, token: str, notification: PushNotification) -> PushResult:
        pass
    
    @abstractmethod
    async def send_batch(self, tokens: List[str], notification: PushNotification) -> List[PushResult]:
        pass


class FCMProvider(PushProviderBase):
    """Firebase Cloud Messaging provider."""
    
    def __init__(self, credentials_path: str = None, project_id: str = None):
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.project_id = project_id or os.getenv("FCM_PROJECT_ID")
        self._client = None
    
    async def _get_client(self):
        """Initialize Firebase Admin SDK."""
        if self._client is None:
            try:
                import firebase_admin
                from firebase_admin import credentials, messaging
                
                if not firebase_admin._apps:
                    if self.credentials_path:
                        cred = credentials.Certificate(self.credentials_path)
                    else:
                        cred = credentials.ApplicationDefault()
                    
                    firebase_admin.initialize_app(cred, {
                        'projectId': self.project_id,
                    })
                
                self._client = messaging
                logger.info("Firebase initialized")
            except ImportError:
                logger.error("firebase-admin not installed. Run: pip install firebase-admin")
                raise
        return self._client
    
    async def send(self, token: str, notification: PushNotification) -> PushResult:
        """Send push notification via FCM."""
        try:
            messaging = await self._get_client()
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title=notification.title,
                    body=notification.body,
                    image=notification.image_url,
                ),
                data={k: str(v) for k, v in notification.data.items()},
                token=token,
                android=messaging.AndroidConfig(
                    priority="high" if notification.priority == NotificationPriority.HIGH else "normal",
                    ttl=notification.ttl,
                    collapse_key=notification.collapse_key,
                    notification=messaging.AndroidNotification(
                        icon=notification.icon,
                        sound=notification.sound or "default",
                        channel_id=notification.channel_id,
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            badge=notification.badge,
                            sound=notification.sound or "default",
                            category=notification.category,
                        ),
                    ),
                ),
            )
            
            # Send async
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, messaging.send, message)
            
            return PushResult(
                success=True,
                provider="fcm",
                message_id=response,
                token=token,
            )
            
        except Exception as e:
            logger.error(f"FCM send failed: {e}")
            return PushResult(
                success=False,
                provider="fcm",
                error=str(e),
                token=token,
            )
    
    async def send_batch(self, tokens: List[str], notification: PushNotification) -> List[PushResult]:
        """Send to multiple tokens."""
        try:
            messaging = await self._get_client()
            
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=notification.title,
                    body=notification.body,
                    image=notification.image_url,
                ),
                data={k: str(v) for k, v in notification.data.items()},
                tokens=tokens,
            )
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, messaging.send_multicast, message)
            
            results = []
            for idx, resp in enumerate(response.responses):
                if resp.success:
                    results.append(PushResult(
                        success=True,
                        provider="fcm",
                        message_id=resp.message_id,
                        token=tokens[idx],
                    ))
                else:
                    results.append(PushResult(
                        success=False,
                        provider="fcm",
                        error=str(resp.exception),
                        token=tokens[idx],
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"FCM batch send failed: {e}")
            return [PushResult(success=False, provider="fcm", error=str(e), token=t) for t in tokens]


class APNSProvider(PushProviderBase):
    """Apple Push Notification Service provider."""
    
    def __init__(
        self,
        key_path: str = None,
        key_id: str = None,
        team_id: str = None,
        bundle_id: str = None,
        use_sandbox: bool = False,
    ):
        self.key_path = key_path or os.getenv("APNS_KEY_PATH")
        self.key_id = key_id or os.getenv("APNS_KEY_ID")
        self.team_id = team_id or os.getenv("APNS_TEAM_ID")
        self.bundle_id = bundle_id or os.getenv("APNS_BUNDLE_ID")
        self.use_sandbox = use_sandbox or os.getenv("APNS_SANDBOX", "false").lower() == "true"
        self._client = None
    
    async def _get_client(self):
        """Initialize APNS client."""
        if self._client is None:
            try:
                from aioapns import APNs, NotificationRequest
                
                self._client = APNs(
                    key=self.key_path,
                    key_id=self.key_id,
                    team_id=self.team_id,
                    topic=self.bundle_id,
                    use_sandbox=self.use_sandbox,
                )
                logger.info("APNS initialized")
            except ImportError:
                logger.error("aioapns not installed. Run: pip install aioapns")
                raise
        return self._client
    
    async def send(self, token: str, notification: PushNotification) -> PushResult:
        """Send push notification via APNS."""
        try:
            from aioapns import NotificationRequest
            
            client = await self._get_client()
            
            request = NotificationRequest(
                device_token=token,
                message={
                    "aps": {
                        "alert": {
                            "title": notification.title,
                            "body": notification.body,
                        },
                        "badge": notification.badge,
                        "sound": notification.sound or "default",
                        "category": notification.category,
                    },
                    **notification.data,
                },
                priority=10 if notification.priority == NotificationPriority.HIGH else 5,
                time_to_live=notification.ttl,
                collapse_key=notification.collapse_key,
            )
            
            response = await client.send_notification(request)
            
            if response.is_successful:
                return PushResult(
                    success=True,
                    provider="apns",
                    message_id=response.notification_id,
                    token=token,
                )
            else:
                return PushResult(
                    success=False,
                    provider="apns",
                    error=response.description,
                    token=token,
                )
                
        except Exception as e:
            logger.error(f"APNS send failed: {e}")
            return PushResult(
                success=False,
                provider="apns",
                error=str(e),
                token=token,
            )
    
    async def send_batch(self, tokens: List[str], notification: PushNotification) -> List[PushResult]:
        """Send to multiple tokens."""
        tasks = [self.send(token, notification) for token in tokens]
        return await asyncio.gather(*tasks)


class WebPushProvider(PushProviderBase):
    """Web Push (VAPID) provider."""
    
    def __init__(
        self,
        vapid_private_key: str = None,
        vapid_public_key: str = None,
        vapid_claims_email: str = None,
    ):
        self.vapid_private_key = vapid_private_key or os.getenv("VAPID_PRIVATE_KEY")
        self.vapid_public_key = vapid_public_key or os.getenv("VAPID_PUBLIC_KEY")
        self.vapid_claims_email = vapid_claims_email or os.getenv("VAPID_CLAIMS_EMAIL", "admin@resonantgenesis.ai")
    
    async def send(self, token: str, notification: PushNotification) -> PushResult:
        """Send web push notification."""
        try:
            from pywebpush import webpush, WebPushException
            
            # Token is JSON subscription info
            subscription_info = json.loads(token)
            
            payload = json.dumps({
                "title": notification.title,
                "body": notification.body,
                "icon": notification.icon,
                "badge": notification.badge,
                "data": notification.data,
            })
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=self.vapid_private_key,
                    vapid_claims={"sub": f"mailto:{self.vapid_claims_email}"},
                    ttl=notification.ttl,
                )
            )
            
            return PushResult(
                success=True,
                provider="web_push",
                token=token,
            )
            
        except Exception as e:
            logger.error(f"Web push send failed: {e}")
            return PushResult(
                success=False,
                provider="web_push",
                error=str(e),
                token=token,
            )
    
    async def send_batch(self, tokens: List[str], notification: PushNotification) -> List[PushResult]:
        """Send to multiple tokens."""
        tasks = [self.send(token, notification) for token in tokens]
        return await asyncio.gather(*tasks)


# ============== MAIN SERVICE ==============

class PushNotificationService:
    """
    Unified push notification service.
    
    Automatically routes to the correct provider based on device token.
    """
    
    def __init__(self):
        self.providers: Dict[PushProvider, PushProviderBase] = {}
        self._init_providers()
    
    def _init_providers(self):
        """Initialize available providers."""
        # FCM
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("FCM_PROJECT_ID"):
            try:
                self.providers[PushProvider.FCM] = FCMProvider()
            except Exception as e:
                logger.warning(f"FCM initialization failed: {e}")
        
        # APNS
        if os.getenv("APNS_KEY_PATH") and os.getenv("APNS_KEY_ID"):
            try:
                self.providers[PushProvider.APNS] = APNSProvider()
            except Exception as e:
                logger.warning(f"APNS initialization failed: {e}")
        
        # Web Push
        if os.getenv("VAPID_PRIVATE_KEY"):
            try:
                self.providers[PushProvider.WEB_PUSH] = WebPushProvider()
            except Exception as e:
                logger.warning(f"Web Push initialization failed: {e}")
        
        if not self.providers:
            logger.warning("No push notification providers configured")
    
    async def send(
        self,
        device: DeviceToken,
        title: str,
        body: str,
        data: Dict[str, Any] = None,
        **kwargs,
    ) -> PushResult:
        """Send push notification to a device."""
        provider = self.providers.get(device.provider)
        if not provider:
            return PushResult(
                success=False,
                provider=device.provider.value,
                error=f"Provider {device.provider.value} not configured",
                token=device.token,
            )
        
        notification = PushNotification(
            title=title,
            body=body,
            data=data or {},
            **kwargs,
        )
        
        return await provider.send(device.token, notification)
    
    async def send_to_user(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Dict[str, Any] = None,
        device_tokens: List[DeviceToken] = None,
        **kwargs,
    ) -> List[PushResult]:
        """Send push notification to all of a user's devices."""
        if not device_tokens:
            # In production, fetch from database
            logger.warning(f"No device tokens provided for user {user_id}")
            return []
        
        notification = PushNotification(
            title=title,
            body=body,
            data=data or {},
            **kwargs,
        )
        
        results = []
        for device in device_tokens:
            provider = self.providers.get(device.provider)
            if provider:
                result = await provider.send(device.token, notification)
                results.append(result)
            else:
                results.append(PushResult(
                    success=False,
                    provider=device.provider.value,
                    error="Provider not configured",
                    token=device.token,
                ))
        
        return results
    
    async def send_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Dict[str, Any] = None,
        **kwargs,
    ) -> PushResult:
        """Send push notification to a topic (FCM only)."""
        fcm = self.providers.get(PushProvider.FCM)
        if not fcm:
            return PushResult(
                success=False,
                provider="fcm",
                error="FCM not configured for topic messaging",
            )
        
        try:
            from firebase_admin import messaging
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data={k: str(v) for k, v in (data or {}).items()},
                topic=topic,
            )
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, messaging.send, message)
            
            return PushResult(
                success=True,
                provider="fcm",
                message_id=response,
            )
            
        except Exception as e:
            logger.error(f"Topic push failed: {e}")
            return PushResult(
                success=False,
                provider="fcm",
                error=str(e),
            )
    
    # ============== CONVENIENCE METHODS ==============
    
    async def send_agent_update(
        self,
        user_id: str,
        agent_name: str,
        status: str,
        device_tokens: List[DeviceToken] = None,
    ) -> List[PushResult]:
        """Send agent status update notification."""
        return await self.send_to_user(
            user_id=user_id,
            title=f"Agent Update: {agent_name}",
            body=f"Status: {status}",
            data={"type": "agent_update", "agent_name": agent_name, "status": status},
            device_tokens=device_tokens,
        )
    
    async def send_task_complete(
        self,
        user_id: str,
        task_name: str,
        success: bool,
        device_tokens: List[DeviceToken] = None,
    ) -> List[PushResult]:
        """Send task completion notification."""
        status = "completed successfully" if success else "failed"
        return await self.send_to_user(
            user_id=user_id,
            title="Task Complete",
            body=f"Task '{task_name}' {status}",
            data={"type": "task_complete", "task_name": task_name, "success": success},
            device_tokens=device_tokens,
        )
    
    async def send_alert(
        self,
        user_id: str,
        message: str,
        severity: str = "info",
        device_tokens: List[DeviceToken] = None,
    ) -> List[PushResult]:
        """Send alert notification."""
        return await self.send_to_user(
            user_id=user_id,
            title=f"Alert: {severity.upper()}",
            body=message,
            data={"type": "alert", "severity": severity},
            priority=NotificationPriority.HIGH if severity in ["critical", "error"] else NotificationPriority.NORMAL,
            device_tokens=device_tokens,
        )


# ============== SINGLETON ==============

_service: Optional[PushNotificationService] = None


def get_push_service() -> PushNotificationService:
    """Get or create push notification service."""
    global _service
    if _service is None:
        _service = PushNotificationService()
    return _service
