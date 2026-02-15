# Core Django imports
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Group, User
from django.db.models import Q

# Local app imports
from app.middleware import get_current_request
from app.models import Parent, Staff, Student

# Map session model label to model class for get_user (avoids pk collision between tables)
_USER_MODEL_MAP = {
    "student": Student,
    "staff": Staff,
    "parent": Parent,
    "user": User,
}

# Fallback order when _auth_user_model is not in session (e.g. old sessions)
_GET_USER_ORDER = [Student, Parent, Staff, User]


class MultiModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate the user based on username (email or phone) and password.
        """
        if username is None or password is None:
            return None

        # Try authenticating as superuser/admin first
        try:
            user = User.objects.get(email=username)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            pass

        # Try authenticating as Staff by phone first
        staff = Staff.objects.filter(phone=username).first()
        if staff:
            if staff.check_password(password):
                return staff

        # Try authenticating as Staff by email
        staff = Staff.objects.filter(email=username).first()
        if staff:
            if staff.check_password(password):
                return staff

        # Try authenticating as Parent by phone
        parent = Parent.objects.filter(phone=username).first()
        if parent:
            if parent.check_password(password):
                return parent

        # Try authenticating as Student by phone
        student = Student.objects.filter(phone=username).first()
        if student:
            if student.check_password(password):
                return student

        # Try authenticating as Student by email
        student = Student.objects.filter(email=username).first()
        if student:
            if student.check_password(password):
                return student

        # Return None if no match
        return None

    def get_user(self, user_id):
        """
        Retrieve a user instance using their ID.
        Uses session key _auth_user_model (set at login) to resolve the correct table
        when multiple user models can share the same pk (e.g. Student id=1 and Staff id=1).
        """
        if user_id is None:
            return None
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None

        request = get_current_request()
        if request and hasattr(request, "session"):
            model_label = request.session.get("_auth_user_model")
            if model_label and model_label in _USER_MODEL_MAP:
                model = _USER_MODEL_MAP[model_label]
                try:
                    return model.objects.get(pk=user_id)
                except model.DoesNotExist:
                    return None

        # No session or legacy session: try in fixed order (Student first so id=1 → Student when possible)
        for model in _GET_USER_ORDER:
            try:
                return model.objects.get(pk=user_id)
            except model.DoesNotExist:
                continue
        return None

    def get_group_permissions(self, user_obj, obj=None):
        """
        Return a set of permission strings that the user has through their groups.
        """
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()

        if isinstance(user_obj, (Staff, Student)):
            if not hasattr(user_obj, "_group_perm_cache"):
                perms = set()
                for group in user_obj.groups.all():
                    perms.update(
                        "%s.%s" % (ct, name)
                        for ct, name in group.permissions.values_list(
                            "content_type__app_label", "codename"
                        )
                    )
                user_obj._group_perm_cache = perms
            return user_obj._group_perm_cache
        else:
            return super().get_group_permissions(user_obj, obj)

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()

        if isinstance(user_obj, (Staff, Student)):
            return self.get_group_permissions(user_obj, obj)
        else:
            return super().get_all_permissions(user_obj, obj)

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_active:
            return False

        if isinstance(user_obj, (Staff, Student)):
            return perm in self.get_all_permissions(user_obj, obj)
        else:
            return super().has_perm(user_obj, perm, obj)
