from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired
from flask_wtf.file import FileField, FileRequired, FileAllowed
from app.config import Config # Import Config to access ALLOWED_EXTENSIONS

class FileUploadForm(FlaskForm):
    file = FileField('File', validators=[
        FileRequired(),
        FileAllowed(Config.ALLOWED_EXTENSIONS, 'Images and PDFs only!')
    ])
    submit = SubmitField('Upload')

class SearchForm(FlaskForm):
    query = StringField('Search', validators=[])
    filter = SelectField('Search Filter', choices=[
        ('nome', 'Name'),
        ('equipamentos', 'Equipments'),
        ('patrimonio_numbers', 'Patrimonio Numbers'),
        ('matricula', 'Matricula'),
        ('funcao', 'Funcao'),
        ('empregador', 'Empregador'),
        ('rg', 'RG'),
        ('cpf', 'CPF'),
        ('processed_data', 'tudo')
    ], default='nome')
    submit = SubmitField('Search')
