from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q
from .constants import AREAS, BUDGET_CHOICES, GENDER_CHOICES, QUESTIONS
from .models import Profile


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
            if avatar.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Ảnh đại diện cần nhỏ hơn 5 MB.")
            content_type = getattr(avatar, "content_type", "").lower()
            name = getattr(avatar, "name", "").lower()
            valid_types = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/pjpeg", "image/x-png"}
            valid_exts = (".jpg", ".jpeg", ".png", ".webp")
            if content_type and content_type not in valid_types and not any(name.endswith(ext) for ext in valid_exts):
                raise forms.ValidationError("Chỉ hỗ trợ ảnh JPG, PNG hoặc WebP.")
        return avatar


class LifestyleQuestionForm(forms.Form):
    def __init__(self, question, *args, **kwargs):
        initial_value = kwargs.pop("initial_value", None)
        super().__init__(*args, **kwargs)
        key, _, label, options = question
        self.question_key = key
        self.fields[key] = forms.ChoiceField(label=label, choices=[(i, option) for i, option in enumerate(options)], widget=forms.RadioSelect, initial=initial_value, error_messages={"required": "Hãy chọn một câu trả lời."})

    def answer(self):
        return int(self.cleaned_data[self.question_key])


class PilotExerciseForm(forms.Form):
    basic_choice = forms.IntegerField(widget=forms.HiddenInput)
    score_choice = forms.IntegerField(widget=forms.HiddenInput)
    basic_trust = forms.IntegerField(min_value=1, max_value=5, widget=forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]), label="Mức độ tin tưởng khi chỉ xem khu vực/ngân sách")
    score_trust = forms.IntegerField(min_value=1, max_value=5, widget=forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]), label="Mức độ tin tưởng khi có điểm lifestyle")
    feedback = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Bạn muốn chia sẻ thêm gì?")
