# YANGI:
import uuid
from datetime import datetime
from rest_framework import serializers
from .models import Organization, User, SupportTicket
from apps.exams.models import Group

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'org_name', 'ceo_name', 'phone', 'email', 'username', 'password',
                  'telegram_chat_id', 'avatar', 'status', 'theme', 'sidebar_collapsed',
                  'created_at', 'updated_at']
        extra_kwargs = {
            'password': {'write_only': True},
            'id': {'required': False},
        }

    def create(self, validated_data):
        validated_data['id'] = validated_data.get('id') or f"org_{self.context.get('request').user.id}_{int(datetime.now().timestamp())}"
        instance = Organization(**validated_data)
        instance.set_password(validated_data['password'])
        instance.save()
        return instance

    def update(self, instance, validated_data):
        if 'password' in validated_data:
            instance.set_password(validated_data['password'])
            del validated_data['password']
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class UserSerializer(serializers.ModelSerializer):
    group_name = serializers.SerializerMethodField()
    group_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'organization', 'name', 'username', 'password', 'plain_password', 'phone',
                  'role', 'telegram_chat_id', 'avatar', 'status', 'theme', 'sidebar_collapsed',
                  'group', 'group_name', 'group_id', 'created_at', 'updated_at']
        extra_kwargs = {
            'password': {'write_only': True},
            'plain_password': {'read_only': True},
            'id': {'required': False},
        }

    def get_group_name(self, obj):
        if obj.group:
            return obj.group.name
        return None

    def get_group_id(self, obj):
        if obj.group:
            return obj.group.id
        return None

    def validate_role(self, value):
        # MUHIM XAVFSIZLIK QOIDASI (butun loyiha bo'ylab yagona nazorat
        # nuqtasi): bu UserSerializer StudentViewSet, UserViewSet va h.k.
        # bir nechta joyda ishlatiladi. 'support' qiymatini HECH KIM (hatto
        # Support foydalanuvchisining o'zi ham) API orqali biror yozuvga
        # bera olmasligi kerak — bu rol faqat to'g'ridan-to'g'ri
        # ma'lumotlar bazasida (masalan boshlang'ich seed skripti orqali)
        # yaratiladi. 'ceo' esa umuman User modelida emas, alohida
        # Organization modelida boshqariladi (OrganizationViewSet/
        # OrganizationSerializer) — shu sabab u ham bu yerdan berilmaydi.
        if value in ('support', 'ceo'):
            raise serializers.ValidationError(
                "Bu rolni ushbu API orqali belgilab bo'lmaydi."
            )
        return value

    def create(self, validated_data):
        validated_data['id'] = f"usr_{int(datetime.now().timestamp())}_{self.context.get('request').user.id}"
        raw_password = validated_data.get('password')
        instance = User(**validated_data)
        if raw_password:
            instance.set_password(raw_password)
            instance.plain_password = raw_password
        instance.save()
        return instance

    def update(self, instance, validated_data):
        if 'password' in validated_data:
            raw_password = validated_data['password']
            instance.set_password(raw_password)
            instance.plain_password = raw_password
            del validated_data['password']
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class StaffSerializer(UserSerializer):
    """
    StaffViewSet (CEO/Support tomonidan tashkilot xodimini yaratish-boshqarish)
    uchun UserSerializer'ning ustidan qo'yilgan qatlam — "role" maydoni
    qat'iy cheklanadi: yangi xodim yaratishda/tahrirlashda FAQAT 'admin'
    tanlanishi mumkin (yangi hiyerarxiya: Support → CEO → Admin, Admin esa
    hech kimni yarata olmaydi).

    MUHIM: 'ceo' va 'support' qiymatlari bu yo'l orqali ASLO berilmaydi —
    frontend select'ida ular ko'rsatilmasa ham, backend darajasida qayta
    tekshiriladi (frontend tekshiruvi yetarli emas, chunki so'rov
    to'g'ridan-to'g'ri API'ga ham yuborilishi mumkin). Bu tekshiruv
    UserSerializer.validate_role() dagi umumiy taqiqni ('support'/'ceo')
    yana ham qattiqroq qiladi — bu yerda boshqa hech qanday qiymatga ('teacher',
    'manager' kabi eskirgan yoki tasodifiy qiymatlarga) ham yo'l qo'yilmaydi.
    """
    ALLOWED_ROLES = ['admin']

    def validate_role(self, value):
        value = super().validate_role(value)
        if value not in self.ALLOWED_ROLES:
            raise serializers.ValidationError(
                "Xodim uchun faqat 'Admin' rolini tanlash mumkin."
            )
        return value


# YANGI:
class SupportTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ['id', 'organization', 'user', 'user_name', 'user_role', 'org_name',
                  'message', 'seen', 'created_at']
        read_only_fields = ['created_at']
        extra_kwargs = {
            'id': {'required': False},
            'organization': {'required': False},
            'user': {'required': False},
            'user_name': {'required': False},
            'user_role': {'required': False},
            'org_name': {'required': False},
        }

    def create(self, validated_data):
        validated_data.setdefault('id', f"tkt_{uuid.uuid4().hex[:12]}")
        return super().create(validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    role = serializers.CharField(required=False)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField(min_length=4)