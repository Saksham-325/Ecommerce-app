from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import render,get_object_or_404,redirect
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


def _get_cart_items(request):
    cart_items = request.session.get('cart', {})
    products = Product.objects.filter(pk__in=cart_items.keys())
    items = []
    subtotal = Decimal('0.00')
    for product in products:
        quantity = min(int(cart_items.get(str(product.pk), 1)), product.stock)
        if quantity < 1:
            continue
        line_total = product.discounted_price * quantity
        subtotal += line_total
        items.append({'product': product, 'quantity': quantity, 'line_total': line_total})
    return items, subtotal


def checkout(request):
    items, subtotal = _get_cart_items(request)
    if not items:
        messages.info(request, 'Add a product to your cart before checkout.')
        return redirect('cart')

    if request.method == 'POST':
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

        cart_items = request.session.get('cart', {})
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
                unit_price = product.discounted_price
                order_lines.append((product, quantity, unit_price))
                current_subtotal += unit_price * quantity
            if stock_changed:
                request.session['cart'] = cart_items
                messages.warning(request, 'Availability changed. Please review your cart and place the order again.')
                return redirect('cart')
            if not order_lines:
                messages.error(request, 'Your cart items are no longer available.')
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
        request.session['cart'] = {}
        return redirect('order_success', order_number=order.order_number)

    return render(request, 'Ecommerce_app/checkout.html', {'items': items, 'subtotal': subtotal})


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
def contacts(request):
    return render(request,'Ecommerce_app/contacts.html')
def wishlist(request):
    return render(request,'Ecommerce_app/wishlist.html')
