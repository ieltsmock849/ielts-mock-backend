from rest_framework.permissions import BasePermission

class IsSupport(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role == 'support'

class IsCEO(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role == 'ceo'

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role in ['ceo', 'admin']

# DIQQAT: 'teacher'/'manager'/'org_support' rollari tizimdan butunlay olib
# tashlandi (endi faqat support/ceo/admin/student mavjud — izoh: models.py).
# Quyidagi IsManager/IsTeacher/IsStaff klasslari boshqa fayllarda hali ham
# import qilingani uchun (ImportError bo'lmasligi uchun) ATAYLAB saqlab
# qolindi, lekin endi mazmunan IsAdmin bilan bir xil (ceo|admin) — organization
# ichidagi yagona "xodim" darajasi endi shu ikkovi.
class IsManager(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role in ['ceo', 'admin']

class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role in ['ceo', 'admin']

class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role in ['ceo', 'admin']

class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role == 'student'

class IsOwnerOrStaff(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'support':
            return True
        if request.user.role in ['ceo', 'admin', 'student']:
            if hasattr(obj, 'organization'):
                return obj.organization_id == request.user.organization_id
            if hasattr(obj, 'exam') and hasattr(obj.exam, 'organization'):
                return obj.exam.organization_id == request.user.organization_id
        if hasattr(obj, 'student') and obj.student_id == request.user.id:
            return True
        if hasattr(obj, 'user') and obj.user_id == request.user.id:
            return True
        return False

class IsOrganizationMember(BasePermission):
    def has_permission(self, request, view):
        if request.user.role == 'support':
            return True
        if request.user.role in ['ceo', 'admin']:
            return request.user.organization_id is not None
        return False

    def has_object_permission(self, request, view, obj):
        # MUHIM: Support uchun ham obyekt darajasida cheklov yo'q emas —
        # bu klass umumiy holatda "organization" maydoni bo'yicha solishtiradi.
        # Support 'has_permission'da global True olgani uchun, ViewSet'larning
        # get_queryset() metodlari support uchun barcha yozuvlarni qaytaradi;
        # shu sabab bu yerda ham support uchun True qaytarish avvalgi xatti-
        # harakatni saqlaydi (backward-compatible).
        if request.user.role == 'support':
            return True
        if hasattr(obj, 'organization'):
            return obj.organization_id == request.user.organization_id
        if hasattr(obj, 'org_id'):
            return obj.org_id == request.user.organization_id
        return False