from django.urls import path
from . import views

urlpatterns = [
    path('',views.home, name='home'),
    path('about/',views.about,name='about'),
    path('cart/',views.cart,name='cart'),
    path('cart/add/<int:pk>/', views.add_to_cart, name='add_to_cart'),
    path('buy-now/<int:pk>/', views.buy_now, name='buy_now'),
    path('checkout/', views.checkout, name='checkout'),
    path('orders/', views.order_history, name='order_history'),
    path('orders/<uuid:order_number>/', views.order_detail, name='order_detail'),
    path('orders/<uuid:order_number>/success/', views.order_success, name='order_success'),
    path('contacts/',views.contacts,name='contacts'),
    path('wishlist/',views.wishlist,name='wishlist'),
    path('product/<int:pk>/',views.product_detail,name='product_detail'),

]

