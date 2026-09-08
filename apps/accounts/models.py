from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class Organization(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    org_name = models.CharField(max_length=200)
    ceo_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=128)
    telegram_chat_id = models.CharField(max_length=50, blank=True)
    avatar = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='active')
    # UI preferences (avval brauzer localStorage'da saqlanardi — endi
    # hisobga bog'liq bo'lgani uchun backend'da, shunda foydalanuvchi
    # qaysi qurilma/brauzerdan kirmasin bir xil ko'rinishni ko'radi).
    theme = models.CharField(max_length=10, default='light')
    sidebar_collapsed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    @property
    def organization_id(self):
        # CEO login qilganda request.user shu Organization obyekti bo'ladi
        # (User emas). Butun kodda request.user.organization_id ishlatilgani
        # uchun bu property CEO holatida ham xuddi shu ishlashini ta'minlaydi.
        return self.id

    class Meta:
        db_table = 'organizations'


class User(models.Model):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('admin', 'Admin'),
        ('ceo', 'CEO'),
        ('support', 'Support'),  # Global, platforma darajasidagi rol. HECH KIM (Support
                                  # o'zi ham) API orqali 'support' qiymatiga ega yozuv
                                  # yarata/tahrirlay/o'chira olmaydi — bu backend darajasida
                                  # qat'iy taqiqlangan (izoh: serializers.py/UserSerializer
                                  # va staff_views.py/UserViewSet).
    )
    # DIQQAT — MUHIM TARIXIY IZOH: ilgari bu yerda 'teacher', 'manager' va
    # 'org_support' degan qo'shimcha rollar bor edi. Yangi talab bo'yicha
    # tizimda FAQAT 3 ta asosiy rol qoladi: support / ceo / admin (+ 'student'
    # alohida, xodim emas). 0005_migrate_legacy_roles_to_admin migratsiyasi
    # ana shu eski qiymatlarga ega BARCHA mavjud yozuvlarni "admin"ga
    # ko'chiradi, shu bilan birga ROLE_CHOICES'dan ham butunlay olib
    # tashlanadi (choices - faqat metama'lumot, DB constraint emas).

    id = models.CharField(max_length=50, primary_key=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=128)
    plain_password = models.CharField(max_length=128, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    telegram_chat_id = models.CharField(max_length=50, blank=True)
    avatar = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='active')
    group = models.ForeignKey('exams.Group', null=True, blank=True, on_delete=models.SET_NULL)
    # UI preferences (avval brauzer localStorage'da saqlanardi — endi
    # hisobga bog'liq bo'lgani uchun backend'da, shunda foydalanuvchi
    # qaysi qurilma/brauzerdan kirmasin bir xil ko'rinishni ko'radi).
    theme = models.CharField(max_length=10, default='light')
    sidebar_collapsed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    class Meta:
        db_table = 'users'


class SupportTicket(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    user_name = models.CharField(max_length=100)
    user_role = models.CharField(max_length=50)
    org_name = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    seen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'support_tickets'
