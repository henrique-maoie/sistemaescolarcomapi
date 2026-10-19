# Sistema Escolar 3B

alunos: Rafael,Luciano,Henrique,Vinicius Ramos e Matheus Domingos 

Projeto desenvolvido pelos alunos do 3B da Escola Orestes Rosolia.

O sistema possui tela de login, painel administrativo, area pedagogica, area comercial, cadastro de alunos, turmas, relatorios, financeiro e controle de vagas por sala/turma.

## Como ligar o sistema no Windows

1. Baixe ou extraia o projeto.
2. Clique duas vezes no arquivo que fica na pasta principal do projeto:

```text
LIGAR_SISTEMA_ESCOLAR.bat
```

3. Deixe a janela preta do servidor aberta.
4. Abra o navegador e acesse:

```text
http://localhost:5000
```

## Outra forma de ligar

Se preferir, tambem pode abrir a pasta:

```text
Alunos3B\school_system
```

E clicar duas vezes no arquivo:

```text
INICIAR_SERVIDOR.bat
```

## Como abrir em outro computador da mesma rede

O computador que abriu o servidor precisa ficar ligado e conectado na mesma rede/Wi-Fi.

Quando o servidor iniciar, ele mostra um endereco parecido com este:

```text
http://192.168.0.25:5000
```

Nos outros computadores, abra esse endereco no navegador.

Se outro computador nao conseguir abrir, execute o arquivo abaixo como administrador no computador servidor:

```text
LIBERAR_ACESSO_REDE_WINDOWS.bat
```

## Acessos do sistema

| Perfil | Email | Senha |
|---|---|---|
| Administrador | admin@escola.com | Mudar@123 |
| Professor | ana@escola.com | Prof@123 |
| Aluno | joao@escola.com | Aluno@123 |
| Comercial | comercial@escola.com | Comercial@123 |
| Financeiro | financeiro@escola.com | Financeiro@123 |
| Pedagogico | pedagogico@escola.com | Pedagogico@123 |

## Acesso principal para teste

Use este login para acessar todas as partes do sistema:

```text
Email: admin@escola.com
Senha: Mudar@123
```

## O que foi melhorado no sistema

- Correcao do servidor e do banco de dados.
- Criacao de usuarios de teste.
- Separacao de acesso por perfil: administrador, professor, aluno, comercial, financeiro e pedagogico.
- Melhorias nas telas de alunos, turmas, salas, relatorios e comercial.
- Tela para visualizar vagas disponiveis por turma/sala.
- Novo layout com menu lateral, cards, tabelas e telas mais modernas.
- Ajustes para abrir em outros computadores da mesma rede.
- Pasta principal renomeada para `Alunos3B`.

## Observacoes

- O servidor funciona na porta `5000`.
- Para parar o sistema, feche a janela preta do servidor ou pressione `Ctrl + C`.
- Se a porta `5000` estiver ocupada, feche outros servidores abertos antes de iniciar novamente.
