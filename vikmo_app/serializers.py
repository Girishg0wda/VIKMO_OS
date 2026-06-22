from rest_framework import serializers
from .models import Product, Inventory, Dealer, Order, OrderItem
from decimal import Decimal

class ProductSerializer(serializers.ModelSerializer):
    # Dynamically read current stock from the OneToOne relationship
    stock = serializers.IntegerField(source='inventory.quantity', read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'sku', 'name', 'category', 'price', 'stock', 'created_at', 'updated_at']


class InventorySerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source='product.sku', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Inventory
        fields = ['id', 'product', 'product_sku', 'product_name', 'quantity', 'updated_at']


class DealerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dealer
        fields = ['id', 'dealer_id', 'name', 'email', 'phone']


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.SerializerMethodField()
    sku = serializers.CharField(source='product.sku', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'sku', 'quantity', 'price_at_order', 'line_total']
        read_only_fields = ['price_at_order']

    def get_line_total(self, obj):
        # Calculate quantity * price_at_order dynamically for response representations
        price = obj.price_at_order or obj.product.price
        return Decimal(obj.quantity) * price


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'order_number', 'dealer', 'status', 'items', 'total_amount', 'created_at', 'updated_at']
        read_only_fields = ['order_number', 'status', 'total_amount']

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        
        # Open a database transaction block for initial order drafting creation safety
        order = Order.objects.create(**validated_data)
        
        total = Decimal('0.00')
        for item_data in items_data:
            product = item_data['product']
            quantity = item_data['quantity']
            
            # Create the item; price_at_order is captured automatically via the model save() hook
            item = OrderItem.objects.create(order=order, product=product, quantity=quantity)
            total += Decimal(quantity) * item.price_at_order
            
        # Update the aggregate total field on the parent order record
        order.total_amount = total
        order.save()
        return order