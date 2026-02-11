from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from app.config import Config # Import Config to access ALLOWED_EXTENSIONS

class FileUploadForm(FlaskForm):
    file = FileField('File', validators=[
        FileRequired(),
        FileAllowed(Config.ALLOWED_EXTENSIONS, 'Images and PDFs only!')
    ])
    group = SelectField('Assign to Group (Optional)', coerce=int, choices=[(0, 'No Group')])
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
