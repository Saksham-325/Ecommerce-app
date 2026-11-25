from django.shortcuts import render,get_object_or_404,redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Product

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

    products = Product.objects.filter(pk__in=cart_items.keys())
    items = []
    subtotal = 0
    for product in products:
        quantity = min(int(cart_items.get(str(product.pk), 1)), product.stock)
        if quantity < 1:
            continue
        line_total = product.discounted_price * quantity
        subtotal += line_total
        items.append({'product': product, 'quantity': quantity, 'line_total': line_total})
    return render(request, 'Ecommerce_app/cart.html', {'items': items, 'subtotal': subtotal})

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
