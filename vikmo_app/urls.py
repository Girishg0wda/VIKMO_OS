from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, DealerViewSet, InventoryViewSet, OrderViewSet, ChannelSyncViewSet

# Pass trailing_slash=False here during initialization instead
router = DefaultRouter(trailing_slash=False)

router.register(r'api/products', ProductViewSet, basename='product')
router.register(r'api/dealers', DealerViewSet, basename='dealer')
router.register(r'api/inventory', InventoryViewSet, basename='inventory')
router.register(r'api/orders', OrderViewSet, basename='order')
router.register(r'api/sync/channel', ChannelSyncViewSet, basename='channelsync')

urlpatterns = [
    path('', include(router.urls)),
]