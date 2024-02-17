import json
import os
import datetime
import shutil
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

app = Flask(__name__)
app_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(app_dir, 'doppelkopf.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Datenbankmodell definieren
class Player(db.Model):
    __tablename__ = 'player'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    losses = db.relationship('Loss', backref='player', lazy=True)
    rounds = db.relationship('Round', back_populates='player', lazy=True)

    def __init__(self, name):
        self.name = name

    def get_total_loss(self):
        return sum(loss.loss_value for loss in self.losses)

class Loss(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    round_num = db.Column(db.Integer, db.ForeignKey('round.round_num'))
    loss_type = db.Column(db.String(50))
    loss_value = db.Column(db.Integer)

class Round(db.Model):
    __tablename__ = 'round'
    round_num = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), primary_key=True)
    round_info = db.Column(db.String(255), default="")
    losses = db.relationship('Loss', backref='round', lazy=True)
    player = db.relationship('Player', back_populates='rounds', lazy=True)

    def __init__(self, round_num, player_id, round_info=""):
        self.round_num = round_num
        self.player_id = player_id
        self.round_info = round_info

# Datenbanktabellen erstellen oder aktualisieren
def create_db():
    with app.app_context():
        db.create_all()

        # Spieler hinzufügen oder vorhandene Spieler beibehalten
        players = ['Denise', 'Elina', 'Lars', 'Flo']
        for player_name in players:
            existing_player = Player.query.filter_by(name=player_name).first()
            if existing_player is None:
                player = Player(name=player_name)
                db.session.add(player)
        db.session.commit()

        # Gesamtverluste abfragen und speichern
        for player_name in players:
            player = Player.query.filter_by(name=player_name).first()
            if player.get_total_loss() == 0:
                total_loss = int(input(f'Gesamtverlust in Cent für Spieler {player_name}: '))
                loss = Loss(player_id=player.id, round_num=0, loss_type='Initial', loss_value=total_loss)
                db.session.add(loss)

        db.session.commit()

        # Alle Runden löschen und neue Runde erstellen
        if Round.query.count() == 0:
            create_new_round()

        # Sichere die Datenbank
        backup_database()

# Loss Types aus JSON laden
def load_loss_types():
    with open('loss_types.json', 'r') as file:
        loss_types = json.load(file)
    return loss_types

# Neue Runde erstellen
def create_new_round():
    if Round.query.count() == 0:
        new_round_num = 1
    else:
        last_round = Round.query.order_by(Round.round_num.desc()).first()
        new_round_num = last_round.round_num + 1

    players = Player.query.all()

    for player in players:
        existing_round = Round.query.filter_by(round_num=new_round_num, player_id=player.id).first()
        if existing_round is None:
            new_round = Round(round_num=new_round_num, player_id=player.id)
            db.session.add(new_round)

    db.session.commit()

    for player in players:
        new_round = Round.query.filter_by(round_num=new_round_num, player_id=player.id).first()
        if new_round.round_info is None:
            # Informationen zur Runde für den Spieler speichern
            player_round_info = f'Runde {new_round_num}:'
            new_round.round_info = player_round_info

    db.session.commit()

    return new_round_num

# Sicherungskopie der Datenbank erstellen
def backup_database():
    backup_dir = os.path.join(app_dir, 'backup')
    os.makedirs(backup_dir, exist_ok=True)

    current_time = datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    backup_file = f'doppelkopf_{current_time}.db'
    backup_path = os.path.join(backup_dir, backup_file)

    shutil.copy2(db_path, backup_path)

# Hauptseite mit Spieler- und Verlustartenauswahl
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        player_names = request.form.getlist('player')
        loss_types = load_loss_types()

        if Round.query.count() == 0:
            create_new_round()

        # Neue Runde erstellen oder aktuelle Runde erhalten
        current_round = Round.query.order_by(Round.round_num.desc()).first()
        current_round_num = current_round.round_num

        if current_round.losses:
            current_round_num += 1
            current_round = Round(round_num=current_round_num, player_id=current_round.player_id)
            db.session.add(current_round)
            db.session.commit()

        for player_name in player_names:
            player = Player.query.filter_by(name=player_name).first()
            print(f'Spieler: {player.name}')

            total_loss_before = player.get_total_loss()
            print(f'Gesamtverlust vorher: {total_loss_before}')

            # Verlustarten und Gesamtverlust für die Runde speichern
            round_num = current_round.round_num
            loss_type_list = []
            total_loss = 0

            for loss_type, loss_value in loss_types.items():
                if loss_type in request.form:
                    loss = Loss(player_id=player.id, round_num=current_round.round_num, loss_type=loss_type, loss_value=loss_value)
                    db.session.add(loss)

                    # Verlustart zur Liste hinzufügen
                    loss_type_list.append(loss_type)
                    # Gesamtverlust aktualisieren
                    total_loss += loss_value

            # Informationen zur Runde für den Spieler speichern
            round_info = Round.query.filter_by(round_num=current_round.round_num, player_id=player.id).first()
            if round_info is None:
                round_info = Round(round_num=current_round.round_num, player_id=player.id, round_info="")
                db.session.add(round_info)

            player_round_info = round_info.round_info + f'\nRunde {round_num}: {", ".join(loss_type_list)}, Gesamtverlust: {total_loss}'
            round_info.round_info = player_round_info

            total_loss_after = player.get_total_loss()
            print(f'Gesamtverlust nachher: {total_loss_after}')

        db.session.commit()
        print('Änderungen erfolgreich in der Datenbank gespeichert.')

    players = Player.query.all()
    current_round = Round.query.order_by(Round.round_num.desc()).first()
    round_infos = Round.query.filter_by(round_num=current_round.round_num).all()
    return render_template('index.html', players=players, loss_types=load_loss_types(), current_round=current_round, round_infos=round_infos)

# Gesamtverluste anzeigen
@app.route('/totals')
def totals():
    players = Player.query.all()
    return render_template('totals.html', players=players)

# Rundenverluste anzeigen
@app.route('/rounds/<string:player_name>')
def rounds(player_name):
    player = Player.query.filter_by(name=player_name).first()
    rounds = Round.query.filter_by(player=player).join(Loss).filter(Loss.round_num == Round.round_num).all()
    return render_template('rounds.html', player=player, rounds=rounds)

# Verluste zurücksetzen
@app.route('/reset', endpoint='reset_losses')
def reset():
    db.drop_all()
    create_db()
    return 'Datenbank zurückgesetzt'

# Datenbank sichern
@app.route('/backup', endpoint='backup_database')
def backup():
    backup_database()
    return 'Datenbank gesichert'

if __name__ == '__main__':
    create_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
