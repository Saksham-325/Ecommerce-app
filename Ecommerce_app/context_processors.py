def cart_count(request):
    cart = request.session.get('cart', {})
    return {'cart_count': sum(max(0, int(quantity)) for quantity in cart.values())}
