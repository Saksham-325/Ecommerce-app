from django.shortcuts import render,get_object_or_404
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
    return render(request,'Ecommerce_app/cart.html')
def contacts(request):
    return render(request,'Ecommerce_app/contacts.html')
def wishlist(request):
    return render(request,'Ecommerce_app/wishlist.html')
