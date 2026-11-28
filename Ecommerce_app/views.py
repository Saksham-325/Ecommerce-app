from decimal import Decimal, InvalidOperation
import base64
import hashlib
import hmac
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseBadRequest
from django.shortcuts import render,get_object_or_404,redirect
from django.urls import reverse
from django.conf import settings
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Order, OrderItem, Product

# Create your views here.
def home(request):
    products=Product.objects.all()
    context = {
        'products':products
    }
    return render(request,'Ecommerce_app/home.html',context=context)

def product_detail(request,pk):
    product = get_object_or_404(Product, id=pk)
    context={
        'product':product
    }
    return render(request,'Ecommerce_app/product_detail.html',context=context)
def about(request):
    return render(request,'Ecommerce_app/about.html')
def cart(request):
    # Opening the cart leaves a Buy Now checkout and returns to the regular cart.
    request.session.pop('buy_now', None)
    cart_items = request.session.get('cart', {})
    if request.method == 'POST':
        product_id = str(request.POST.get('product_id', ''))
        action = request.POST.get('action')
        if action == 'remove':
            cart_items.pop(product_id, None)
            messages.info(request, 'Item removed from your cart.')
        elif action == 'update':
            product = get_object_or_404(Product, pk=product_id)
            try:
                quantity = int(request.POST.get('quantity', 1))
            except (TypeError, ValueError):
                quantity = 1
            if quantity < 1:
                cart_items.pop(product_id, None)
                messages.info(request, 'Item removed from your cart.')
            else:
                cart_items[product_id] = min(quantity, product.stock)
                if product.stock == 0:
                    cart_items.pop(product_id, None)
                elif quantity > product.stock:
                    messages.warning(request, f'Only {product.stock} of {product.name} are available.')
        request.session['cart'] = cart_items
        return redirect('cart')

    items, subtotal = _get_cart_items(request)
    return render(request, 'Ecommerce_app/cart.html', {'items': items, 'subtotal': subtotal})


def _get_cart_items(request, cart_items=None):
    if cart_items is None:
        cart_items = request.session.get('cart', {})
    products = Product.objects.filter(pk__in=cart_items.keys())
    items = []
    subtotal = Decimal('0.00')
    for product in products:
        quantity = min(int(cart_items.get(str(product.pk), 1)), product.stock)
        if quantity < 1:
            continue
        line_total = product.discounted_price.quantize(Decimal('0.01')) * quantity
        subtotal += line_total
        items.append({'product': product, 'quantity': quantity, 'line_total': line_total})
    return items, subtotal


def checkout(request):
    buy_now_items = request.session.get('buy_now')
    is_buy_now = bool(buy_now_items)
    cart_items = buy_now_items if is_buy_now else request.session.get('cart', {})
    items, subtotal = _get_cart_items(request, cart_items)
    if not items:
        if is_buy_now:
            request.session.pop('buy_now', None)
            messages.error(request, 'This product is no longer available.')
            return redirect('cart')
        messages.info(request, 'Add a product to your cart before checkout.')
        return redirect('cart')

    if request.method == 'POST':
        if request.POST.get('payment_method') != 'esewa':
            messages.error(request, 'Please select eSewa as your payment method.')
            return render(request, 'Ecommerce_app/checkout.html', {'items': items, 'subtotal': subtotal})
        details = {
            'full_name': request.POST.get('full_name', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'phone': request.POST.get('phone', '').strip(),
            'address': request.POST.get('address', '').strip(),
            'city': request.POST.get('city', '').strip(),
            'postal_code': request.POST.get('postal_code', '').strip(),
            'note': request.POST.get('note', '').strip(),
        }
        if not all(details[key] for key in ('full_name', 'email', 'phone', 'address', 'city')):
            messages.error(request, 'Please complete all required delivery details.')
            return render(request, 'Ecommerce_app/checkout.html', {'items': items, 'subtotal': subtotal, 'details': details})
        try:
            validate_email(details['email'])
        except ValidationError:
            messages.error(request, 'Please enter a valid email address.')
            return render(request, 'Ecommerce_app/checkout.html', {'items': items, 'subtotal': subtotal, 'details': details})

        with transaction.atomic():
            products = Product.objects.select_for_update().filter(pk__in=cart_items.keys())
            products_by_id = {str(product.pk): product for product in products}
            order_lines = []
            current_subtotal = Decimal('0.00')
            stock_changed = False
            for product_id, quantity in list(cart_items.items()):
                product = products_by_id.get(str(product_id))
                if not product:
                    cart_items.pop(str(product_id), None)
                    stock_changed = True
                    continue
                quantity = int(quantity)
                if quantity > product.stock:
                    stock_changed = True
                    if product.stock:
                        cart_items[str(product_id)] = product.stock
                    else:
                        cart_items.pop(str(product_id), None)
                    continue
                if quantity < 1:
                    continue
                unit_price = product.discounted_price.quantize(Decimal('0.01'))
                order_lines.append((product, quantity, unit_price))
                current_subtotal += unit_price * quantity
            if stock_changed:
                messages.warning(request, 'Availability changed. Please review your cart and place the order again.')
                if is_buy_now and cart_items:
                    request.session['buy_now'] = cart_items
                    return redirect('checkout')
                if is_buy_now:
                    request.session.pop('buy_now', None)
                    return redirect('cart')
                request.session['cart'] = cart_items
                return redirect('cart')
            if not order_lines:
                messages.error(request, 'Your cart items are no longer available.')
                if is_buy_now:
                    request.session.pop('buy_now', None)
                return redirect('cart')
            order = Order.objects.create(subtotal=current_subtotal, **details)
            for product, quantity, unit_price in order_lines:
                OrderItem.objects.create(
                    order=order, product=product, product_name=product.name,
                    unit_price=unit_price, quantity=quantity,
                )
                product.stock -= quantity
                product.save(update_fields=['stock'])

        order_numbers = request.session.get('order_numbers', [])
        order_numbers.append(str(order.order_number))
        request.session['order_numbers'] = order_numbers
        if is_buy_now:
            request.session.pop('buy_now', None)
        else:
            request.session['cart'] = {}
        return redirect('esewa_start', order_number=order.order_number)

    return render(request, 'Ecommerce_app/checkout.html', {'items': items, 'subtotal': subtotal})


def _esewa_signature(fields, secret):
    message = ','.join(f'{name}={fields[name]}' for name in fields)
    digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def esewa_start(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    if str(order.order_number) not in request.session.get('order_numbers', []):
        return redirect('home')
    if order.payment_status == 'paid':
        return redirect('order_success', order_number=order.order_number)
    if order.payment_status == 'failed':
        return render(request, 'Ecommerce_app/payment_result.html', {'order': order, 'result': 'failed'})

    amount = f'{order.subtotal:.2f}'
    signed_fields = {
        'total_amount': amount,
        'transaction_uuid': str(order.order_number),
        'product_code': settings.ESEWA_PRODUCT_CODE,
    }
    callback = request.build_absolute_uri(reverse('esewa_return'))
    callback += '?' + urlencode({'order': str(order.order_number)})
    form_fields = {
        'amount': amount,
        'tax_amount': '0',
        **signed_fields,
        'product_service_charge': '0',
        'product_delivery_charge': '0',
        'success_url': callback,
        'failure_url': callback,
        'signed_field_names': ','.join(signed_fields),
        'signature': _esewa_signature(signed_fields, settings.ESEWA_SECRET_KEY),
    }
    return render(request, 'Ecommerce_app/esewa_redirect.html', {
        'form_url': settings.ESEWA_FORM_URL, 'fields': form_fields,
    })


def esewa_return(request):
    order = get_object_or_404(Order, order_number=request.GET.get('order'))
    if str(order.order_number) not in request.session.get('order_numbers', []):
        return redirect('home')
    if order.payment_status == 'paid':
        return redirect('order_success', order_number=order.order_number)
    if order.payment_status == 'failed':
        return render(request, 'Ecommerce_app/payment_result.html', {'order': order, 'result': 'failed'})

    if 'data' in request.GET:
        try:
            encoded = request.GET['data']
            response_fields = json.loads(base64.b64decode(encoded, validate=True))
            signed_names = response_fields['signed_field_names'].split(',')
            signed_fields = {name: response_fields[name] for name in signed_names}
            valid_signature = hmac.compare_digest(
                _esewa_signature(signed_fields, settings.ESEWA_SECRET_KEY),
                response_fields['signature'],
            )
        except (KeyError, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return HttpResponseBadRequest('Invalid eSewa response.')
        if not valid_signature or response_fields.get('transaction_uuid') != str(order.order_number):
            return HttpResponseBadRequest('eSewa response could not be verified.')

    try:
        query = urlencode({
            'product_code': settings.ESEWA_PRODUCT_CODE,
            'total_amount': f'{order.subtotal:.2f}',
            'transaction_uuid': str(order.order_number),
        })
        with urlopen(f'{settings.ESEWA_STATUS_URL}?{query}', timeout=10) as response:
            status_data = json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError):
        return render(request, 'Ecommerce_app/payment_result.html', {'order': order, 'result': 'pending'})

    try:
        matches_order = (
            status_data.get('product_code') == settings.ESEWA_PRODUCT_CODE
            and status_data.get('transaction_uuid') == str(order.order_number)
            and Decimal(str(status_data.get('total_amount', '0')).replace(',', '')) == order.subtotal
        )
    except (AttributeError, TypeError, ValueError, InvalidOperation):
        matches_order = False
    if not isinstance(status_data, dict):
        return render(request, 'Ecommerce_app/payment_result.html', {'order': order, 'result': 'pending'})
    if status_data.get('status') == 'COMPLETE' and matches_order:
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk)
            if locked_order.payment_status == 'pending':
                locked_order.payment_status = 'paid'
                locked_order.payment_reference = status_data.get('ref_id', '')
                locked_order.status = 'processing'
                locked_order.save(update_fields=['payment_status', 'payment_reference', 'status'])
        return redirect('order_success', order_number=order.order_number)

    if status_data.get('status') in ('NOT_FOUND', 'CANCELED') and matches_order:
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk)
            if locked_order.payment_status == 'pending':
                for item in locked_order.items.select_related('product'):
                    if item.product_id:
                        Product.objects.filter(pk=item.product_id).update(stock=F('stock') + item.quantity)
                locked_order.payment_status = 'failed'
                locked_order.save(update_fields=['payment_status'])
        return render(request, 'Ecommerce_app/payment_result.html', {'order': order, 'result': 'failed'})
    return render(request, 'Ecommerce_app/payment_result.html', {'order': order, 'result': 'pending'})


def order_success(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    if str(order.order_number) not in request.session.get('order_numbers', []):
        return redirect('home')
    return render(request, 'Ecommerce_app/order_success.html', {'order': order})


def order_detail(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    if str(order.order_number) not in request.session.get('order_numbers', []):
        return redirect('home')
    return render(request, 'Ecommerce_app/order_detail.html', {'order': order})


def order_history(request):
    order_numbers = request.session.get('order_numbers', [])
    orders = Order.objects.filter(order_number__in=order_numbers).order_by('-created_at')
    return render(request, 'Ecommerce_app/order_history.html', {'orders': orders})

@require_POST
def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk)
    cart_items = request.session.get('cart', {})
    current_quantity = int(cart_items.get(str(product.pk), 0))
    if product.stock < 1:
        messages.error(request, f'{product.name} is currently out of stock.')
    elif current_quantity >= product.stock:
        messages.warning(request, f'Only {product.stock} of {product.name} are available.')
    else:
        cart_items[str(product.pk)] = current_quantity + 1
        request.session['cart'] = cart_items
        messages.success(request, f'{product.name} was added to your cart.')
    return redirect('cart')


@require_POST
def buy_now(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if product.stock < 1:
        messages.error(request, f'{product.name} is currently out of stock.')
        return redirect('product_detail', pk=product.pk)
    request.session['buy_now'] = {str(product.pk): 1}
    return redirect('checkout')


def contacts(request):
    return render(request,'Ecommerce_app/contacts.html')
def wishlist(request):
    return render(request,'Ecommerce_app/wishlist.html')
