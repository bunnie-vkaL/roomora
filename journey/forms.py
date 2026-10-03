import math
import uuid

from django import forms
from django.forms import inlineformset_factory
from PIL import Image

from . import models as m
from .services import CLAUSES


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = m.LivingPreferences
        exclude = ["profile", "version"]
        labels = {"move_in_from": "Có thể chuyển vào từ", "move_in_until": "Muộn nhất có thể chuyển vào",
                  "needs": "Nhu cầu về nơi ở (được hiển thị trên hồ sơ)", "sleep_at": "Giờ đi ngủ thường ngày",
                  "wake_at": "Giờ thức dậy", "quiet_from": "Muốn yên tĩnh từ", "quiet_until": "Đến",
                  "total_monthly_budget": "Trần tổng chi phí mỗi tháng (VND, tùy chọn)",
                  "upfront_budget": "Trần tiền đầu kỳ (VND, tùy chọn)", "notifications_enabled": "Nhận thông báo trong ứng dụng"}
        widgets = {"needs": forms.Textarea(attrs={"rows": 3}),
                   **{key: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d") for key in ["move_in_from", "move_in_until"]},
                   **{key: forms.TimeInput(attrs={"type": "time"}, format="%H:%M") for key in ["sleep_at", "wake_at", "quiet_from", "quiet_until"]}}

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


class RoomForm(forms.ModelForm):
    class Meta:
        model = m.RoomOption
        fields = ["title", "url", "area", "address", "notes"]
        labels = {"title": "Tên căn / phòng", "url": "Link tham khảo", "area": "Khu vực", "address": "Địa chỉ (nếu đã biết)", "notes": "Thông tin và điều cần hỏi"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class RoomCostForm(forms.ModelForm):
    class Meta:
        model = m.RoomCost
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


RoomCostFormSet = inlineformset_factory(m.RoomOption, m.RoomCost, form=RoomCostForm, extra=3, can_delete=True, max_num=20, validate_max=True)


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
        model = m.ImagePin
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
        model = m.ViewingPlan
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
        model = m.MoveInTask
        fields = ["title", "assignee", "due_at"]
        labels = {"title": "Việc cần làm", "assignee": "Người phụ trách", "due_at": "Hạn hoàn thành"}
        widgets = {"due_at": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, workspace, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Profile
        self.fields["assignee"].queryset = Profile.objects.filter(workspaces__workspace=workspace, workspaces__active=True)
        self.fields["assignee"].label_from_instance = lambda profile: profile.name
