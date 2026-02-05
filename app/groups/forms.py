from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, ValidationError
from app.models import User

class GroupForm(FlaskForm):
    name = StringField('Group Name', validators=[DataRequired()])
    description = TextAreaField('Description')
    submit = SubmitField('Create Group')

class AddMemberForm(FlaskForm):
    email = StringField('User Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Add Member')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if not user:
            raise ValidationError('No user found with this email.')
