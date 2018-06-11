import socket
import sys
import threading
from threading import Thread
import time
import datetime
import json
import math
import logging


PORT = 55151

class Roteador:
    def __init__(self, ip, period, server_socket):
        self.ip = ip
        self.roteadores = {self.ip: 0}
        self.period = int(period)
        self.vetor_distancia = {ip: {ip: 0}}
        self.socket = server_socket
        self.fila_proximo_roteador = {}
        self.ultimo_update = {}

    #####################################################
    #####################################################
    #####
    #####       Utils
    #####
    #####################################################
    #####################################################

    def add_roteador(self, ip, distance):
        self.roteadores.update({ip: distance})
        
        if ip not in self.vetor_distancia:
            self.vetor_distancia.update({ip: {ip: distance}})

        elif distance < self.vetor_distancia[ip]:
            self.vetor_distancia[ip].update({ip: distance})

    def del_roteador(self, ip):
        del self.roteadores[ip]
        del self.vetor_distancia[ip]
        if ip in self.fila_proximo_roteador:
            del self.fila_proximo_roteador[ip]

        for roteador in self.vetor_distancia:
            self.vetor_distancia[roteador].pop(ip, None)

        for roteador in self.fila_proximo_roteador:
            if ip in self.fila_proximo_roteador[roteador]:
                self.fila_proximo_roteador[roteador].remove(ip)

    def trace(self, destination):
        self.envia_trace(destination)

    # executa um comando recebido
    def executa_comando(self, comando):
        comando = comando.split(' ')

        if comando[0] == 'add':
            self.add_roteador(comando[1], int(comando[2]))

        elif comando[0] == 'del':
            self.del_roteador(comando[1])

        elif comando[0] == 'trace':
            self.trace(comando[1])

        elif comando[0] == 'quit':
            sys.exit(1)

    # define qual o tipo da mensagem recebida
    def define_tipo_mensagem(self, mensagem):
        mensagem = mensagem.decode('utf-8')
        json_mensagem = json.loads(mensagem)

        message_type = json_mensagem['type']

        if message_type == 'update':
            self.atualiza_tabela(json_mensagem)
        elif message_type == 'data':
            self.recebe_dados(json_mensagem)
        elif message_type == 'trace':
            self.faz_trace(json_mensagem)

    # adiciona roteadores passados pelo arquivo de entrada
    def inicializa_pelo_arquivo(self, startup):
        with open(startup) as f:
            comandos = f.readlines()

        for comando in comandos:
            self.executa_comando(comando.rstrip())

    # define o proximo roteador para um destino dado
    def proximo_roteador(self, destination):
        menor = math.inf

        for roteador in self.vetor_distancia[destination]:
            if roteador not in self.fila_proximo_roteador:
                self.fila_proximo_roteador[roteador] = []

            if self.vetor_distancia[destination][roteador] <= menor:
                menor = self.vetor_distancia[destination][roteador]

        for roteador in self.vetor_distancia[destination]:
            if self.vetor_distancia[destination][roteador] == menor:
                if roteador not in self.fila_proximo_roteador[destination]:
                    if roteador in self.roteadores:
                        self.fila_proximo_roteador[destination].append(roteador)

        proximo = self.fila_proximo_roteador[destination].pop(0)
        self.fila_proximo_roteador[destination].append(proximo)

        return proximo

    # remove roteadores inativos
    def verifica_roteador_indisponivel(self):
        hora_atual = datetime.datetime.now()
        removido = False

        for roteador in self.ultimo_update:
            tolerancia = self.ultimo_update[roteador] + datetime.timedelta(seconds=self.period*4)

            if hora_atual > tolerancia:
                removido = roteador
                if roteador in self.roteadores:
                    del self.roteadores[roteador]

                for roteador_2 in self.vetor_distancia:
                    self.vetor_distancia[roteador_2].pop(roteador, None)

                for roteador_2 in self.fila_proximo_roteador:
                    if roteador in self.fila_proximo_roteador[roteador_2]:
                        self.fila_proximo_roteador[roteador_2].remove(roteador)

        if removido != False:
            del self.ultimo_update[removido]
            del self.vetor_distancia[removido]
            if removido in self.fila_proximo_roteador:
                del self.fila_proximo_roteador[removido]

    #####################################################
    #####################################################
    #####
    #####       Tratamento de trace
    #####
    #####################################################
    #####################################################

    def cria_mensagem_trace(self, destination):
        message = {
            "type": "trace",
            "source": self.ip,
            "destination": destination,
            "hops": [self.ip]
        }
        msg = json.dumps(message, indent=2)
        return msg.encode('utf-8')

    def envia_trace(self, destination):
        socket = self.socket
        message = self.cria_mensagem_trace(destination)

        socket.sendto(message, (self.proximo_roteador(destination), PORT))

    def faz_trace(self, json_mensagem):
        socket = self.socket
        destination = json_mensagem['destination']

        if destination == self.ip:
            json_mensagem['hops'].append(self.ip)
            self.envia_dados(json_mensagem['source'], json.dumps(json_mensagem))
        else:
            json_mensagem['hops'].append(self.ip)
            message = json.dumps(json_mensagem).encode('utf-8')
            socket.sendto(message, (self.proximo_roteador(destination), PORT))


    #####################################################
    #####################################################
    #####
    #####       Tratamento de atualizacao
    #####
    #####################################################
    #####################################################

    def menores_distancias(self, destination):
        novo_vetor_distancias = {}
        for roteador in self.vetor_distancia:
            menor_distancia = math.inf
            for distancia in self.vetor_distancia[roteador]:
                if self.vetor_distancia[roteador][distancia] < menor_distancia:
                    menor_distancia = self.vetor_distancia[roteador][distancia]
            if roteador != destination:
                novo_vetor_distancias[roteador] = menor_distancia

        return novo_vetor_distancias

    # cria uma mensagem de atualizacao para enviar aos roteadores vizinhos
    def cria_mensagem_atualizacao(self, destination):
        message = {
            "type": "update",
            "source": self.ip,
            "destination": destination,
            "distances": self.menores_distancias(destination)
        }
        msg = json.dumps(message, indent=2)
        return msg.encode('utf-8')

    # atualiza a tabela de distancias
    def atualiza_tabela(self, json_mensagem):
        self.ultimo_update[json_mensagem['source']] = datetime.datetime.now()
        for roteador in json_mensagem['distances']:
            if json_mensagem['source'] in self.roteadores:
                distance = json_mensagem['distances'][roteador] + self.roteadores[json_mensagem['source']]
                if roteador not in self.vetor_distancia:
                    self.vetor_distancia.update({roteador: {roteador: int(distance)}})
                elif json_mensagem['source'] not in self.vetor_distancia[roteador]:
                    self.vetor_distancia[roteador].update({json_mensagem['source']: int(distance)})

    # envia a tabela de roteadores vizinhos atualizada
    def envia_atualizacao(self):
        socket = self.socket
        vizinhos = self.roteadores

        for vizinho in vizinhos:
            if vizinho != self.ip:
                mensagem = self.cria_mensagem_atualizacao(vizinho)
                socket.sendto(mensagem, (vizinho, PORT))

    #####################################################
    #####################################################
    #####
    #####       Tratamento de dados
    #####
    #####################################################
    #####################################################

    def cria_mensagem_dados(self, destination, dados):
        message = {
            "type": "data",
            "source": self.ip,
            "destination": destination,
            "payload": dados
        }
        msg = json.dumps(message, indent=2)
        return msg.encode('utf-8')

    def envia_dados(self, destination, message):
        mensagem = self.cria_mensagem_dados(destination, message)
        socket = self.socket
        if destination in self.roteadores:
            socket.sendto(mensagem, (destination, PORT))
        else:
            socket.sendto(mensagem, (self.proximo_roteador(destination), PORT))

    def recebe_dados(self, json_mensagem):
        destination = json_mensagem['destination']
        dados = json_mensagem['payload']

        if destination == self.ip:
            print(dados)
        else:
            self.envia_dados(destination, dados)

    #####################################################
    #####################################################
    #####
    #####       Threads
    #####
    #####################################################
    #####################################################

    # thread responsavel pela comunicacao interna entre roteadores
    def recebe_mensagens(self):
        socket = self.socket
        while True:
            message, address = socket.recvfrom(1024)
            self.define_tipo_mensagem(message)

    # thread responsavel por atualizar as rotas
    def update_rotas(self):
        tempo_inicio = time.perf_counter()
        period = self.period

        while True:
            tempo_atual = time.perf_counter()

            if (tempo_atual - tempo_inicio) > period:
                self.verifica_roteador_indisponivel()
                self.envia_atualizacao()
                tempo_inicio = time.perf_counter()

    # thread responsavel por receber input do usuario
    def input_usuario(self, startup):
        if startup != False:
            self.inicializa_pelo_arquivo(startup)

        while True:
            comando = input()
            
            self.executa_comando(comando)

# inicia as tres threads
def inicia_roteador(addr, period, startup):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((addr, PORT))

    roteador = Roteador(addr, period, server_socket)

    # cria thread atualizacao de rotas
    Thread(target = roteador.update_rotas,).start()

    # cria thread para comunicacao entre roteadores
    Thread(target = roteador.recebe_mensagens,).start()

    # cria thread para comandos do usuarios
    Thread(target = roteador.input_usuario, args = (startup,),).start()


if __name__ == "__main__":
    startup = False

    versao_python = str(sys.version_info.major) + '.' + str(sys.version_info.minor)

    if (versao_python != '3.6'):
        logging.warning('Este programa foi desenvolvido utilizando a versao 3.6 do Python')
        logging.warning('Algo pode funcionar diferente do esperado em outras versões')

    try:
        if len(sys.argv) > 4:
            for i in range(0, len(sys.argv)):
                if sys.argv[i] == '--addr':
                    addr = sys.argv[i+1]
                elif sys.argv[i] == '--update-period':
                    period = sys.argv[i+1]
                elif sys.argv[i] == '--startup-commands':
                    startup = sys.argv[i+1]
        else:
            addr = sys.argv[1]
            period = sys.argv[2]
            
            if len(sys.argv) == 4:
                startup = sys.argv[3]
    except:
        print('Algo errado ocorreu')
        print('Utilize o formato python3.6 router.py --addr 127.0.1.1 --update-period 3 --startup-commands 1.txt')
        print('Ou python3.6 router.py 127.0.1.1 3 1.txt')
    
    inicia_roteador(addr, period, startup)