"""Roomora Forms: Account, Profile, Living Preferences, Rooms, and Agreements."""
import math
import uuid
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory
from django.db.models import Q
from PIL import Image

from .constants import AREAS, BUDGET_CHOICES, GENDER_CHOICES, QUESTIONS
from .models import (
    ImagePin,
    LivingPreferences,
    MoveInTask,
    Profile,
    RoomCost,
    RoomOption,
    ViewingPlan,
)
from .services import CLAUSES


# ==============================================================================
# Authentication & Account Lifecycle Forms
# ==============================================================================

class RegistrationForm(UserCreationForm):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            "placeholder": "Địa chỉ email của bạn",
            "autocomplete": "email",
            "autocapitalize": "none"
        })
    )

    class Meta:
        model = User
        fields = ("email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "password1" in self.fields:
            self.fields["password1"].label = "Mật khẩu"
            self.fields["password1"].widget.attrs.update({"placeholder": "Tối thiểu 8 ký tự"})
        if "password2" in self.fields:
            self.fields["password2"].label = "Xác nhận mật khẩu"
            self.fields["password2"].widget.attrs.update({"placeholder": "Nhập lại mật khẩu"})

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise forms.ValidationError("Vui lòng nhập địa chỉ email.")
        if User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).exists():
            raise forms.ValidationError("Email này đã được sử dụng. Vui lòng đăng nhập hoặc sử dụng email khác.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["email"].strip().lower()
        user.username = email
        user.email = email
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email hoặc tên đăng nhập",
        widget=forms.TextInput(attrs={
            "autofocus": True,
            "placeholder": "Email hoặc tên đăng nhập",
            "autocomplete": "username",
            "autocapitalize": "none",
            "autocorrect": "off",
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "password" in self.fields:
            self.fields["password"].label = "Mật khẩu"
            self.fields["password"].widget.attrs.update({"placeholder": "Nhập mật khẩu"})

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username is not None and password:
            username = username.strip()
            user_obj = User.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            ).first()

            auth_username = user_obj.username if user_obj else username
            self.user_cache = authenticate(
                self.request, username=auth_username, password=password
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    "Tên đăng nhập/email hoặc mật khẩu không chính xác. Vui lòng thử lại.",
                    code="invalid_login",
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


# ==============================================================================
# Demographic Profile & Lifestyle Preferences Forms
# ==============================================================================

class ProfileForm(forms.ModelForm):
    areas = forms.MultipleChoiceField(label="Khu vực mong muốn", choices=[(a, a) for a in AREAS], widget=forms.CheckboxSelectMultiple)
    gender = forms.ChoiceField(label="Giới tính (tuỳ chọn)", required=False, choices=[("", "Chọn giới tính")] + GENDER_CHOICES)
    birth_year = forms.IntegerField(label="Năm sinh", min_value=1900, max_value=2008)
    hometown = forms.CharField(label="Quê quán", max_length=100)
    bio = forms.CharField(label="Giới thiệu ngắn (tuỳ chọn)", max_length=280, required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ví dụ: Mình yêu một không gian sống gọn gàng, tôn trọng riêng tư và thích nấu ăn vào cuối tuần."}))
    rent_min = forms.TypedChoiceField(label="Ngân sách tối thiểu (VND/tháng)", choices=BUDGET_CHOICES, coerce=int)
    rent_max = forms.TypedChoiceField(label="Ngân sách tối đa (VND/tháng)", choices=BUDGET_CHOICES, coerce=int)
    avatar = forms.FileField(label="Ảnh đại diện (tuỳ chọn)", required=False, widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))

    class Meta:
        model = Profile
        fields = ["name", "age", "birth_year", "gender", "hometown", "bio", "avatar", "areas", "rent_min", "rent_max", "contact_type", "contact_value"]
        labels = {"name": "Tên hiển thị", "age": "Tuổi", "birth_year": "Năm sinh", "gender": "Giới tính (tuỳ chọn)", "hometown": "Quê quán", "bio": "Giới thiệu ngắn (tuỳ chọn)", "rent_min": "Ngân sách tối thiểu (VND/tháng)", "rent_max": "Ngân sách tối đa (VND/tháng)", "contact_type": "Kênh liên hệ", "contact_value": "Zalo hoặc số điện thoại"}

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not avatar:
            return avatar
        from django.core.files.uploadedfile import UploadedFile
        if isinstance(avatar, UploadedFile):
            if avatar.size > 8 * 1024 * 1024:
                raise forms.ValidationError("Ảnh đại diện cần nhỏ hơn 8 MB.")
            content_type = getattr(avatar, "content_type", "").lower()
            name = getattr(avatar, "name", "").lower()
            valid_types = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/pjpeg", "image/x-png"}
            valid_exts = (".jpg", ".jpeg", ".png", ".webp")
            if content_type and content_type not in valid_types and not any(name.endswith(ext) for ext in valid_exts):
                raise forms.ValidationError("Chỉ hỗ trợ ảnh JPG, PNG hoặc WebP.")
        return avatar


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = LivingPreferences
        exclude = ["profile", "version"]
        labels = {
            "move_in_from": "Có thể chuyển vào từ",
            "move_in_until": "Muộn nhất có thể chuyển vào",
            "needs": "Nhu cầu về nơi ở (được hiển thị trên hồ sơ)",
            "sleep_at": "Giờ đi ngủ thường ngày",
            "wake_at": "Giờ thức dậy",
            "quiet_from": "Muốn yên tĩnh từ",
            "quiet_until": "Đến",
            "total_monthly_budget": "Trần tổng chi phí mỗi tháng (VND, tùy chọn)",
            "upfront_budget": "Trần tiền đầu kỳ (VND, tùy chọn)",
            "notifications_enabled": "Nhận thông báo trong ứng dụng",
        }
        widgets = {
            "needs": forms.Textarea(attrs={"rows": 3}),
            **{key: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d") for key in ["move_in_from", "move_in_until"]},
            **{key: forms.TimeInput(attrs={"type": "time"}, format="%H:%M") for key in ["sleep_at", "wake_at", "quiet_from", "quiet_until"]},
        }

    def clean(self):
        data = super().clean()
        start, end = data.get("move_in_from"), data.get("move_in_until")
        if start and end and end < start:
            self.add_error("move_in_until", "Ngày cuối phải sau hoặc bằng ngày bắt đầu.")
        for start_key, end_key in [("sleep_at", "wake_at"), ("quiet_from", "quiet_until")]:
            if bool(data.get(start_key)) != bool(data.get(end_key)):
                self.add_error(end_key, "Nhập cả giờ bắt đầu và kết thúc, hoặc để cả hai trống.")
            elif data.get(start_key) and data[start_key] == data[end_key]:
                self.add_error(end_key, "Giờ bắt đầu và kết thúc cần khác nhau.")
        return data


class LifestyleQuestionForm(forms.Form):
    def __init__(self, question, *args, **kwargs):
        initial_value = kwargs.pop("initial_value", None)
        super().__init__(*args, **kwargs)
        key, _, label, options = question
        self.question_key = key
        self.fields[key] = forms.ChoiceField(
            label=label,
            choices=[(i, option) for i, option in enumerate(options)],
            widget=forms.RadioSelect,
            initial=initial_value,
            error_messages={"required": "Hãy chọn một câu trả lời."}
        )

    def answer(self):
        return int(self.cleaned_data[self.question_key])


class PilotExerciseForm(forms.Form):
    basic_choice = forms.IntegerField(widget=forms.HiddenInput)
    score_choice = forms.IntegerField(widget=forms.HiddenInput)
    basic_trust = forms.IntegerField(min_value=1, max_value=5, widget=forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]), label="Mức độ tin tưởng khi chỉ xem khu vực/ngân sách")
    score_trust = forms.IntegerField(min_value=1, max_value=5, widget=forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]), label="Mức độ tin tưởng khi có điểm lifestyle")
    feedback = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Bạn muốn chia sẻ thêm gì?")


# ==============================================================================
# Shared Rooms, Photos, Viewing Plans, and Consensus Forms
# ==============================================================================

class RoomForm(forms.ModelForm):
    class Meta:
        model = RoomOption
        fields = ["title", "url", "area", "address", "notes"]
        labels = {"title": "Tên căn / phòng", "url": "Link tham khảo", "area": "Khu vực", "address": "Địa chỉ (nếu đã biết)", "notes": "Thông tin và điều cần hỏi"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class RoomCostForm(forms.ModelForm):
    class Meta:
        model = RoomCost
        fields = ["label", "period", "state", "amount", "source"]
        labels = {"label": "Khoản tiền", "period": "Chu kỳ", "state": "Mức xác minh", "amount": "VND", "source": "Nguồn / điều cần kiểm tra"}

    def clean(self):
        data = super().clean()
        if not data.get("label"):
            return data
        if data.get("state") == "unknown":
            if data.get("amount") is not None:
                self.add_error("amount", "Khoản chưa biết phải để trống số tiền.")
        elif data.get("amount") is None:
            self.add_error("amount", "Nhập số tiền khi đánh dấu đã biết hoặc ước tính.")
        if data.get("amount") is not None and data["amount"] > 10**12:
            self.add_error("amount", "Số tiền tối đa là 1.000 tỷ VND.")
        return data


RoomCostFormSet = inlineformset_factory(
    RoomOption, RoomCost, form=RoomCostForm, extra=3, can_delete=True, max_num=20, validate_max=True
)


class ImageUploadForm(forms.Form):
    image = forms.ImageField(label="Ảnh căn / bằng chứng đi xem")
    caption = forms.CharField(max_length=200, required=False, label="Mô tả ảnh")

    def clean_image(self):
        uploaded = self.cleaned_data["image"]
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Ảnh cần nhỏ hơn 5 MB.")
        try:
            image = Image.open(uploaded)
            if image.format not in ["JPEG", "PNG", "WEBP"] or image.width * image.height > 20_000_000:
                raise forms.ValidationError("Chỉ dùng JPG, PNG hoặc WebP, tối đa 20 triệu điểm ảnh.")
            extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image.format]
            image.verify()
        except (Image.DecompressionBombError, OSError, ValueError):
            raise forms.ValidationError("Tệp không phải ảnh hợp lệ.")
        finally:
            uploaded.seek(0)
        uploaded.name = uuid.uuid4().hex + extension
        return uploaded


class PinForm(forms.ModelForm):
    class Meta:
        model = ImagePin
        fields = ["x", "y", "question"]

    def clean(self):
        data = super().clean()
        for key in ("x", "y"):
            value = data.get(key)
            if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
                self.add_error(key, "Vị trí phải nằm trong ảnh.")
        return data


class ViewingForm(forms.ModelForm):
    class Meta:
        model = ViewingPlan
        fields = ["at", "meeting_point"]
        labels = {"at": "Thời gian đề xuất", "meeting_point": "Điểm hẹn"}
        widgets = {"at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}


class AgreementForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label in CLAUSES.items():
            self.fields[key] = forms.CharField(label=label, required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))


class TaskForm(forms.ModelForm):
    class Meta:
        model = MoveInTask
        fields = ["title", "assignee", "due_at"]
        labels = {"title": "Việc cần làm", "assignee": "Người phụ trách", "due_at": "Hạn hoàn thành"}
        widgets = {"due_at": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = Profile.objects.filter(workspaces__workspace=workspace, workspaces__active=True)
        self.fields["assignee"].label_from_instance = lambda profile: profile.name


__all__ = [
    "RegistrationForm",
    "EmailAuthenticationForm",
    "ProfileForm",
    "PreferencesForm",
    "LifestyleQuestionForm",
    "PilotExerciseForm",
    "RoomForm",
    "RoomCostForm",
    "RoomCostFormSet",
    "ImageUploadForm",
    "PinForm",
    "ViewingForm",
    "AgreementForm",
    "TaskForm",
]
