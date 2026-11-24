from django.urls import path
from . import views

urlpatterns = [
    path('',views.home, name='home'),
    path('about/',views.about,name='about'),
    path('cart/',views.cart,name='cart'),
    path('contacts/',views.contacts,name='contacts'),
    path('wishlist/',views.wishlist,name='wishlist'),
    path('product/<int:pk>/',views.product_detail,name='product_detail'),

]

