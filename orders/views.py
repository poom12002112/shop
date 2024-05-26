from django.shortcuts import render
from django.views.generic import View, TemplateView,FormView
from django.http import JsonResponse,HttpResponseRedirect,HttpResponse,Http404
from products.models import Product
import base64
import pickle
from .forms import OrderForm  # 确保你导入了正确的表单类
from .models import Order  # 确保你导入了正确的模型类
from .ecpay_payment_sdk import ECPayPaymentSdk
from datetime import datetime
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt,csrf_protect,requires_csrf_token
from products.models import RelationalProduct
from django.contrib import messages
from django.views.generic.edit import FormView
from django.contrib.sessions.models import Session
from django.db.models import Max




class AddCartView(View):

    def get(self, request, *args, **kwargs):
        product_id = self.kwargs.get('product_id', '')
        cart_str = request.COOKIES.get('cart', '')
        if product_id:
            if cart_str:
                cart_bytes = cart_str.encode()
                cart_bytes = base64.b64decode(cart_bytes)
                cart_dict = pickle.loads(cart_bytes)
            else:
                cart_dict = {}
            if product_id in cart_dict:
                cart_dict[product_id]['count'] += 1
            else:
                cart_dict[product_id] = {
                    'count': 1,
                }
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
        context = {}
        context["status"] = 200
        response = JsonResponse(context)
        response.set_cookie("cart", cart_str)
        return response

class DeleteCartView(View):

    def get(self, request, *args, **kwargs):
        product_id = self.kwargs.get('product_id', '')
        cart_str = request.COOKIES.get('cart', '')
        if product_id:
            if cart_str:
                cart_bytes = cart_str.encode()
                cart_bytes = base64.b64decode(cart_bytes)
                cart_dict = pickle.loads(cart_bytes)
            else:
                cart_dict = {}
            if product_id in cart_dict:
                del cart_dict[product_id]
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
        context = {}
        context["status"] = 200
        response = JsonResponse(context)
        response.set_cookie("cart", cart_str)
        return response

class CartView(TemplateView):
    template_name = "orders/cart.html"

    def get(self, request, *args, **kwargs):
        cart_str = request.COOKIES.get('cart', '')
        product_dict = {}
        if cart_str:
            cart_bytes = cart_str.encode()
            cart_bytes = base64.b64decode(cart_bytes)
            cart_dict = pickle.loads(cart_bytes)
            product_dict = cart_dict.copy()
            for product_id in cart_dict:
                if product := Product.objects.filter(id=product_id):
                    product_dict[product_id]["product"] = product.first()
                else:
                    del product_dict[product_id]
        context = self.get_context_data(**kwargs)
        context["product_dict"] = product_dict
        return self.render_to_response(context)


class CheckoutView(FormView):
    template_name = "orders/checkout.html"   # 结帐页面
    form_class = OrderForm
    success_url = 'orders/confirmation.html' # 前往付款页面

    # 获取购物车cookie
    def get_cart_cookie(self, request):
        cart_str = request.COOKIES.get('cart', '')
        cart_dict = {}
        if cart_str:
            cart_bytes = cart_str.encode()
            cart_bytes = base64.b64decode(cart_bytes)
            cart_dict = pickle.loads(cart_bytes)
        return cart_dict
    
    # 处理GET请求，获取购物车信息并渲染页面
    def get(self, request, *args, **kwargs):
        cart_dict = self.get_cart_cookie(request)
        if cart_dict:
            product_dict = {}
            total = 0
            for product_id, product_data in cart_dict.items():
                product = Product.objects.filter(id=product_id).first()
                if product:
                    product_dict[product_id] = {
                        'product': {
                            'id': product.id,
                            'name': product.name,
                            'price': product.price,
                            'image_url': product.product_image_set.first().image.url if product.product_image_set.first() else None,
                            # Add other required fields here
                        },
                        'count': product_data['count']
                    }
                    total += int(product_data['count']) * int(product.price)
            # 将订单摘要数据存储在会话中
            request.session['product_dict'] = product_dict
            request.session['total'] = total
        else:
            # 如果购物车为空，则清除会话中的订单摘要数据
            request.session.pop('product_dict', None)
            request.session.pop('total', None)
        context = self.get_context_data(**kwargs)
        # 将订单摘要数据和总计金额传递到模板中
        context["product_dict"] = product_dict
        context["total"] = total
        return self.render_to_response(context)
    
    # 添加CSRF保护
    @method_decorator(csrf_protect)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    # 处理表单验证成功的情况
    def form_valid(self, form):
        # 保存订单信息
        self.object = form.save(commit=False)
        cart_dict = self.get_cart_cookie(self.request)
        
        if cart_dict:
            product_details = []
            total = 0
            for product_id, product_data in cart_dict.items():
                product = Product.objects.filter(id=product_id).first()
                if product:
                    # 构建商品名称和数量的组合字符串
                    product_details.append(f"{product.name} ({product_data['count']})")
                    total += int(product_data['count']) * int(product.price)
                    
            # 更新订单的总价和产品信息字段
            self.object.total = total
            self.object.product_names = ', '.join(product_details)

            # 保存订单对象
            self.object.save()
            
            # 创建相关的产品关系对象
            for product_id, product_data in cart_dict.items():
                product = Product.objects.filter(id=product_id).first()
                if product:
                    RelationalProduct.objects.create(order=self.object, product=product, number=product_data['count'])
        
        # 清除会话中的订单摘要数据
        self.request.session.pop('product_dict', None)
        self.request.session.pop('total', None)
        
        context = self.get_context_data(form=form)
        context['order_id'] = self.object.order_id
        return render(self.request, self.success_url, context=context)

    # 处理表单验证失败的情况
    def form_invalid(self, form):
        # 在表单验证失败时显示错误消息，并从会话中获取订单摘要数据
        messages.error(self.request, "Please correct the errors below.")
        product_dict = self.request.session.get('product_dict', {})
        total = self.request.session.get('total', 0)
        context = self.get_context_data(form=form, product_dict=product_dict, total=total)
        return self.render_to_response(context)



    
class ECPayView(TemplateView):
    template_name = "orders/ecpay.html"

    def post(self, request, *args, **kwargs):
        scheme = request.is_secure() and "https" or "http"
        domain = request.META['HTTP_HOST']

        order_id = request.POST.get("order_id")
        order = Order.objects.get(order_id=order_id)
        product_list = "#".join([product.name for product in order.product.all()])
        order_params = {
            'MerchantTradeNo': order.order_id,
            'StoreID': '',
            'MerchantTradeDate': datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
            'PaymentType': 'aio',
            'TotalAmount': order.total,
            'TradeDesc': order.order_id,
            'ItemName': product_list,
            'ReturnURL': f'{scheme}://{domain}/orders/return/',  # ReturnURL
            'ChoosePayment': 'ALL',
            'ClientBackURL': f'{scheme}://{domain}/orders/checkout/',  # 返回商店按鈕
            'ItemURL': f'{scheme}://{domain}/products/list/',  # 商品銷售網址
            'Remark': '交易備註',
            'ChooseSubPayment': '',
            'OrderResultURL': f'{scheme}://{domain}/orders/orderresult/',  # 付款完成後
            'NeedExtraPaidInfo': 'Y',
            'DeviceSource': '',
            'IgnorePayment': '',
            'PlatformID': '',
            'InvoiceMark': 'N',
            'CustomField1': '',
            'CustomField2': '',
            'CustomField3': '',
            'CustomField4': '',
            'EncryptType': 1,
        }
        # 建立實體
        ecpay_payment_sdk = ECPayPaymentSdk(
            MerchantID='3002607',
            HashKey='pwFHCqoQZGmho4w6',
            HashIV='EkRm7iFT261dpevs'
        )
        # 產生綠界訂單所需參數
        final_order_params = ecpay_payment_sdk.create_order(order_params)

        # 產生 html 的 form 格式
        action_url = 'https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5'  # 測試環境
        # action_url = 'https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5' # 正式環境
        ecpay_form = ecpay_payment_sdk.gen_html_post_form(action_url, final_order_params)
        context = self.get_context_data(**kwargs)
        context['ecpay_form'] = ecpay_form
        return self.render_to_response(context)
    
class OrderSuccessView(TemplateView):
    template_name = "orders/order_success.html"

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

class ReturnView(View):
    
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        ecpay_payment_sdk = ECPayPaymentSdk(
            MerchantID='3002607',
            HashKey='pwFHCqoQZGmho4w6',
            HashIV='EkRm7iFT261dpevs'
        )
        res = request.POST.dict()
        back_check_mac_value = request.POST.get('CheckMacValue')
        check_mac_value = ecpay_payment_sdk.generate_check_value(res)
        if check_mac_value == back_check_mac_value:
            response = HttpResponse('1|OK')
            clear_cart(response)
            return response
        return HttpResponse('0|Fail')
    
class OrderResultView(View):
    
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(OrderResultView, self).dispatch(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):

        ecpay_payment_sdk = ECPayPaymentSdk(
            MerchantID='3002607',
            HashKey='pwFHCqoQZGmho4w6',
            HashIV='EkRm7iFT261dpevs'
        )
        res = request.POST.dict()
        back_check_mac_value = request.POST.get('CheckMacValue')
        order_id = request.POST.get('MerchantTradeNo')
        rtnmsg = request.POST.get('RtnMsg')
        rtncode = request.POST.get('RtnCode')
        check_mac_value = ecpay_payment_sdk.generate_check_value(res)
        if check_mac_value == back_check_mac_value and rtnmsg == 'Succeeded' and rtncode == '1':
            order = Order.objects.get(order_id=order_id)
            order.status = '付款成功'
            order.save()
            response = HttpResponseRedirect('/orders/order_success/')
            clear_cart(response)
            return response
        else:
            order = Order.objects.get(order_id=order_id)
            order.status = '付款失敗'
            order.save()
            return HttpResponseRedirect('/orders/order_fail/')

class OrderFailView(TemplateView):
    template_name = "orders/order_fail.html"

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)
    
from django.http import JsonResponse
from django.views import View

class SearchOrders(View):
    
    def post(self, request):
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        
        # 在这里通过搜索数据库，获取相应的订单数据，这里仅为示例
        # 假设你已经定义了一个 Order 模型
        # orders = Order.objects.filter(phone=phone, email=email)

        # 为了示例，这里直接返回一些假数据
        orders = [{'id': 1, 'product': 'Product A', 'quantity': 2}, {'id': 2, 'product': 'Product B', 'quantity': 1}]

        return JsonResponse({'orders': orders})


class IndexView(TemplateView):
    template_name = "orders/index.html"

    def get(self, request, *args, **kwargs):
        # 渲染初始页面，这里可能不需要任何逻辑
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        # 获取电话和电子邮件
        phone = request.POST.get('phone')
        email = request.POST.get('email')

        if phone and email:
            # 如果电话和电子邮件都存在，则认为成功
            success = True

            # 获取符合条件的订单内容，并按订单编号降序排列
            matching_orders = Order.objects.filter(phone=phone, email=email).order_by('-id')
            if matching_orders.exists():
                # 找到符合条件的订单
                orders = matching_orders.values()
            else:
                # 没有找到符合条件的订单
                orders = None

        else:
            success = False
            orders = None

        context = self.get_context_data(**kwargs)
        context["success"] = success
        context["orders"] = orders
        return self.render_to_response(context)
    
def clear_cart(response):
    response.delete_cookie('cart')


