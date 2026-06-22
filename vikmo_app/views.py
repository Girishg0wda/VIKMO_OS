from django.shortcuts import render
import os
import json
from rest_framework.views import APIView
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from .models import Product, Inventory, Dealer, Order, OrderItem
from .serializers import ProductSerializer, InventorySerializer, DealerSerializer, OrderSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class DealerViewSet(viewsets.ModelViewSet):
    queryset = Dealer.objects.all()
    serializer_class = DealerSerializer

class InventoryViewSet(viewsets.ModelViewSet):
    queryset = Inventory.objects.all()
    serializer_class = InventorySerializer

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        order = self.get_object()

        if order.status != 'DRAFT':
            return Response(
                {"error": f"Invalid transition. Cannot confirm an order in {order.status} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                order_items = order.items.all()
                product_ids = [item.product_id for item in order_items]

                inventories = Inventory.objects.select_for_update().filter(product_id__in=product_ids)
                inventory_map = {inv.product_id: inv for inv in inventories}

                errors = []
                for item in order_items:
                    inv = inventory_map.get(item.product_id)
                    if not inv or inv.quantity < item.quantity:
                        available = inv.quantity if inv else 0
                        errors.append(
                            f"Insufficient stock for {item.product.name}. Available: {available}, Requested: {item.quantity}."
                        )

                if errors:
                    return Response({"error": errors}, status=status.HTTP_400_BAD_REQUEST)

                for item in order_items:
                    inv = inventory_map[item.product_id]
                    inv.quantity -= item.quantity
                    inv.save()

                order.status = 'CONFIRMED'
                order.save()

            return Response({"status": "Order confirmed and stock allocated successfully."}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"Transaction failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def deliver(self, request, pk=None):
        order = self.get_object()

        if order.status != 'CONFIRMED':
            return Response(
                {"error": f"Invalid transition. Only CONFIRMED orders can be marked as DELIVERED. Current status: {order.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = 'DELIVERED'
        order.save()
        return Response({"status": "Order marked as delivered successfully."}, status=status.HTTP_200_OK)


# FIXED: This class is now completely independent and flush with the left wall!
class ChannelSyncViewSet(viewsets.ViewSet):
    """
    Handles reconciling and updating local data structures 
    idempotently based on external supplier JSON feeds.
    """
    
    def create(self, request):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        feed_path = os.path.join(base_dir, 'channel_feed.json')

        if not os.path.exists(feed_path):
            return Response(
                {"error": f"Mock channel feed file not found at {feed_path}"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            with open(feed_path, 'r') as file:
                feed_products = json.load(file)
        except Exception as e:
            return Response(
                {"error": f"Failed to parse source file JSON format: {str(e)}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for item in feed_products:
                sku = item.get('sku')
                name = item.get('name')
                price = item.get('price')
                category = item.get('category', '')
                stock = item.get('stock', 0)

                if not sku:
                    continue

                product, created = Product.objects.update_or_create(
                    sku=sku,
                    defaults={
                        'name': name,
                        'price': price,
                        'category': category
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                Inventory.objects.update_or_create(
                    product=product,
                    defaults={'quantity': stock}
                )

        return Response({
            "status": "Channel synchronization execution complete.",
            "conflict_policy": "Channel Wins (External values overwrite local discrepancies)",
            "products_created": created_count,
            "products_updated": updated_count
        }, status=status.HTTP_200_OK)