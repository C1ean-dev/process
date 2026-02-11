from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired

class DocumentForm(FlaskForm):
    nome = StringField('Nome Completo', validators=[DataRequired()])
    funcao = StringField('Função', validators=[DataRequired()])
    empregador = StringField('Empregador', validators=[DataRequired()], default='Falcão Bauer')
    matricula = StringField('Matrícula', validators=[DataRequired()])
    rg = StringField('RG', validators=[DataRequired()])
    cpf = StringField('CPF', validators=[DataRequired()])
    equipamentos = TextAreaField('Equipamentos', validators=[DataRequired()])
    group = SelectField('Atribuir ao Grupo', coerce=int)
    submit = SubmitField('Gerar e Enviar Documento')
