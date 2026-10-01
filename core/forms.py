from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .constants import AREAS, BUDGET_CHOICES, GENDER_CHOICES, QUESTIONS
from .models import Profile


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(label="Email")
    class Meta:
        model = User
        fields = ("email", "password1", "password2")
    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Email này đã được sử dụng.")
        return email
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"].lower()
        user.email = user.username
        if commit: user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email")


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
        self.fields[key] = forms.ChoiceField(label=label, choices=[(i, option) for i, option in enumerate(options)], widget=forms.RadioSelect, initial=initial_value)

    def answer(self):
        return int(self.cleaned_data[self.question_key])


class PilotExerciseForm(forms.Form):
    basic_choice = forms.IntegerField(widget=forms.HiddenInput)
    score_choice = forms.IntegerField(widget=forms.HiddenInput)
    basic_trust = forms.IntegerField(min_value=1, max_value=5, widget=forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]), label="Mức độ tin tưởng khi chỉ xem khu vực/ngân sách")
    score_trust = forms.IntegerField(min_value=1, max_value=5, widget=forms.RadioSelect(choices=[(i, str(i)) for i in range(1, 6)]), label="Mức độ tin tưởng khi có điểm lifestyle")
    feedback = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}), label="Bạn muốn chia sẻ thêm gì?")
