# TelegramScammerChatRoom
This program wastes the time of scammers talking to a chat robot, so they don't have time to scam as many people. This is the equivalent of Telegram messages coming to your telegram from an unknown number. Uses N8N and python application
# How create telegram password
Obtaining api_id
In order to obtain an API id and develop your own application using the Telegram API you need to do the following:
 - Sign up for Telegram using an official application.
 - Log in to your Telegram core: https://my.telegram.org.
 - Go to "API development tools" and fill out the form.
You will get basic addresses as well as the api_id and api_hash parameters required for user authorization.
For the moment each number can only have one api_id connected to it

## Make the enviroment file in yor root folder
```.env
API_ID=1234567890
API_HASH=a1234567890123456asdfghjkl23445
REST_URL=http://localhost:5678/webhook/telegramApi
#REST_URL=http://localhost:5678/webhook-test/telegramApi
PHONE=+35812345678
```
# install
Install all python requirements
``` bash
pip install requirements.txt
```


