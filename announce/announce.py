import os
import json
import math
import time
import glob
from pprint import pprint
import tracery
from tracery.modifiers import base_english
from twitch import TwitchClient
import tweepy
import requests

def save_config():
    json.dump(config, open('config.json', 'w'), indent=2)

def get_twitch_token(token, refresh=False):
    data = {
        'client_id': config['twitch']['client_id'],
        'client_secret': config['twitch']['client_secret'],
    }
    if refresh:
        data['refresh_token'] = token
        data['grant_type'] = 'refresh_token'
    else:
        data['code'] = token
        data['redirect_uri'] = config['twitch']['redirect_url']
        data['grant_type'] = 'authorization_code'

    print('sending token request to twitter:')
    pprint(data)
    auth_r = requests.post('https://id.twitch.tv/oauth2/token', data)
    auth_r.raise_for_status()
    resp = auth_r.json()
    config['twitch']['access_token'] = resp['access_token']
    config['twitch']['refresh_token'] = resp('refresh_token')
    save_config()
    return resp['access_token']

# Load config
config_changed = False
try:
    config = json.load(open('config.json'))
except FileNotFoundError:
    config = {
        'twitter': {'interval': '50'},
        'twitch': {'redirect_url': 'https://masterbase.at/twitch/tokengen/'},
        'testmode': True,
        "timestamp_path": "annoucmentbot.timestamp",
        "rec_path": "/var/rec",
    }
testmode = config['testmode']
tweet_length = 200

# Update config if needed
if 'consumer_key' not in config['twitter']:
    config['twitter']['consumer_key'] = input('Twitter Consumer Key: ')
    config_changed = True

if 'consumer_secret' not in config['twitter']:
    config['twitter']['consumer_secret'] = input('Twitter Consumer Secret: ')
    config_changed = True

auth_live = tweepy.OAuthHandler(config['twitter']['consumer_key'], config['twitter']['consumer_secret'])
auth_main = tweepy.OAuthHandler(config['twitter']['consumer_key'], config['twitter']['consumer_secret'])

if 'access_token_live' not in config['twitter']:
    try:
        redirect_url = auth_live.get_authorization_url()
    except tweepy.TweepError:
        print('Error! Failed to get request token.')
    print('please go to this url sign in with the livesteam account and enter the verifier code here %s' %
        redirect_url)
    verifier = input('verifier code: ')
    try:
        auth_live.get_access_token(verifier)
    except tweepy.TweepError:
        print('Error! Failed to get access token.')

    config['twitter']['access_token_live'] = auth_live.access_token
    config['twitter']['access_token_secret_live'] = auth_live.access_token_secret
    config_changed = True

if 'access_token_main' not in config['twitter']:
    try:
        redirect_url = auth_main.get_authorization_url()
    except tweepy.TweepError:
        print('Error! Failed to get request token.')
    print('please go to this url sign in with the main account and enter the verifier code here %s' %
        redirect_url)
    verifier = input('verifier code: ')
    try:
        auth_main.get_access_token(verifier)
    except tweepy.TweepError:
        print('Error! Failed to get access token.')

    config['twitter']['access_token_main'] = auth_main.access_token
    config['twitter']['access_token_secret_main'] = auth_main.access_token_secret
    config_changed = True

if 'client_id' not in config['twitch']:
    config['twitch']['client_id'] = input('Twitch Client ID: ')
    config_changed = True

if 'client_secret' not in config['twitch']:
    config['twitch']['client_secret'] = input('Twitch Client Secret: ')
    config_changed = True

if 'access_token' not in config['twitch']:
    print("please got to %s#clientid=%s&scopes=user_read%%20channel_read%%20channel_editor%%20channel_stream and get a authorization token" %
        (config['twitch']['redirect_url'], config['twitch']['client_id']))
    config['twitch']['access_token'] = input('Twitch Access Token: ')
    config_changed = True

if 'discord_webhook' not in config:
    config['discord_webhook'] = input('Discord Webhook URL: ')
    config_changed = True

#if 'access_token' not in config['twitch'] or 'refresh_token' not in config['twitch']:
#    print("please got to %s#clientid=%s&scopes=user_read%%20channel_editor%%20channel_stream and get a authorization token" %
#        (config['twitch']['redirect_url'], config['twitch']['client_id']))
#    authorization_token = input('Authorization Token: ')
#    get_twitch_token(authorization_token)


# Save config
if config_changed:
    print('Saving config…')
    save_config()
    print()

# Auth and API Init
auth_live.set_access_token(config['twitter']['access_token_live'], config['twitter']['access_token_secret_live'])
auth_main.set_access_token(config['twitter']['access_token_main'], config['twitter']['access_token_secret_main'])
twitter_live = tweepy.API(auth_live, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)
twitter_main = tweepy.API(auth_main, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)
twitch = TwitchClient(client_id=config['twitch']['client_id'], oauth_token=config['twitch']['access_token'])
twitch_channel = twitch.channels.get()

#resolve twitch communities if communities is set in conifg
twitch_communities = None
if 'communities' in config['twitch']:
    if len(config['twitch']['communities']) > 3:
        print('ERROR to many twtich communities set, some will be ignored')
    twitch_communities = []
    for community in config['twitch']['communities'][0:3]:
        print('resolving id of twitch community with name "%s"... ' % (community,), end='', flush=True)
        try:
            twitch_community = twitch.communities.get_by_name(community)
            print('found! %s' % twitch_community.id)
            twitch_communities.append(twitch_community)
        except requests.exceptions.HTTPError:
            print('ERROR\naborting communities lookup and disabeling communities change')
            twitch_communities = None
            break


rules = {
    'youtube_url': ['https://www.youtube.com/channel/UCamUJpSJpJuXeAKx-seRHgg/live'],
    'twitch_url': ['https://www.twitch.tv/evilscientress'],
    'any_url': [ '#youtube_url#', '#twitch_url#' ],
    'both_urls': [ '#youtube_url# #twitch_url#', '#twitch_url# #youtube_url#' ],

    'main_hashtag': [ '\\#JennysLabLive' ],
    'continued_hashtag': [ '\\#JennysLabOnAir' ],

    'stream': [ 'stream', 'stream', 'stream', 'live stream', 'broadcast', 'livestream' ],
    'started': [ 'started', 'started', 'started', 'going', 'going', 'on air', 'roling' ],
    'going': ['going', 'on air', 'roling' ],

    'lab': [ 'lab', 'lab', 'shop', 'electronics lab' ],
    'exclam': [ '!', '!', '!', '~', '~', '~', '.', '.', '.', '!!'],
    'excomma': [ ',', '#exclam#' ],
    'excite': [ 'yay', 'neat', 'cool', 'sweet', 'nice' ],
    'excite_cute': [ 'uwu', 'UwU', ':3' ],

    'starting': [
        'Getting another #stream# #started##exclam#',
        'Going LIVE#exclam#',
        'Starting up another #stream#;',
        'Let\'s get another #stream# #started##exclam#',
        'Streaming now#exclam#',
        '#stream.capitalize# time#exclam#',
        'Broadcasting LIVE#exclam#',
        'Going LIVE from the #lab##exclam#',
        'LIVE On Air from the #lab##exclam#',
    ],

    'continuing': [
        '#excite.capitalize##excomma# #stream.capitalize# is still going#exclam#',
        '#stream.capitalize# is still #going# #excite_cute# –',
        '#stream.capitalize# is still #going##exclam#',
        '#stream.capitalize# still happening#exclam#',
        'Still #stream#ing#exclam#',
        'Still #stream#ing #excite_cute# –',
    ],

    'content': [
        '#firstContent.capitalize#, #secondContent#, and #bonusContent##exclam#',
        '#firstContent.capitalize# & #secondContent##exclam#',
        '#firstContent.capitalize# & #secondContent##exclam#',
        '#firstContent.capitalize# & #secondContent##exclam#',
    ],

    'firstContent': [ 'electronics', 'electronics', 'hardware', 'hardware', 'engineering', 'PCBs', 'circuits' ],
    'secondContent': [ 'experiments', 'science', 'reverse engineering', 'learning something', 'cool gadgets', 'blinky stuff', 'coding'],
    'bonusContent': [ 'latex', 'magic smoke (sometimes)' ],

    'chat_msg': ['#starting# #content#\n#youtube_url#'],
    'first_tweet': ['#starting# #content# #main_hashtag#\n#both_urls#'],
    'periodic_tweet': ['#continuing# #content# #continued_hashtag#\n#both_urls#'],
    'twitch_status': ['Jenny\'s #lab# – #content#'],
}

grammar = tracery.Grammar(rules)
grammar.add_modifiers(base_english)


def minutes_since_last_tweet():
    mtime = 0
    try:        
        mtime = os.stat(config['twitter']['timestamp_path']).st_mtime
    except Exception as e:
        pass
    if testmode and False:
        print("last tweet %d minute(s) ago" % ((time.time() - mtime)/60))
    return math.floor((time.time() - mtime)/60)


def tweet(template, media=None):
    while True:
        text = grammar.flatten(template)
        if len(text) <= tweet_length:
            break
    if not testmode:
        try:
            if media is None:
                status_live = twitter_live.update_status(text)
            else:
                status_live = twitter_live.update_with_media(media, text)
            #pprint(status_live)
            try:
                status_main = twitter_main.retweet(status_live.id)
                #pprint(status_main)
            except tweepy.TweepError:
                print('Error! Failed to retweet annoucment on main account')
        except tweepy.TweepError:
            print('Error! Failed to tweet annoucment tweet on live account')
    else:
        if media is None:
            print('would tweet:\n%s' % (text,))
        else:
            print('would tweet:\n%s\nwith media%s' % (text, media))
    try:
        open(config['twitter']['timestamp_path'], 'w').close()
    except OSError as e:
        print('ERORR failed to write timestamp file exiting to prevent spamming')
        exit(1)

def twitch_set_status(twitch_status):
    if not testmode:
        twitch.channels.update(channel_id=twitch_channel.id, status=twitch_status, game='Creative', delay=0)
    else:
        print('would set twitch status: %s' % (twitch_status,))

#set twitch communities to list defined in config
def twitch_set_communities(twitch_communities):
    if twitch_communities is None:
        return
    if type(twitch_communities) is not list:
        raise TypeError('ERROR twitch_communities must be a list')

    if not testmode:
        data={'community_ids': [community.id for community in twitch_communities]}
        headers = {
            'Authorization': 'OAuth ' + config['twitch']['access_token'],
            'Accept': 'application/vnd.twitchtv.v5+json',
        }
        r = requests.put('https://api.twitch.tv/kraken/channels/%s/communities' % (twitch_channel.id,),
            json=data, headers=headers)
    else:
        print('would set twitch communities to: %s' %
            ', '.join([community.display_name for community in twitch_communities]))


def discord_sendmsg(content, tts=None, embeds=None, webhook_url=config['discord_webhook']):
    data={'content': content, 'tts': tts, 'embeds': embeds}
    r = requests.post(webhook_url, json=data)
    if r.status_code < 200 or r.status_code >= 300:    
        print("error posting discord message: status code %d\n%s" % (r.status_code, r.text))

def discord(template):
    chat_msg = grammar.flatten(template)
    if not testmode:
        discord_sendmsg(chat_msg)
    else:
        print('would send discord chat msg:\n%s' % (chat_msg,))


def get_last_screenshot():
    screenshot_filetypes = {'png', 'jpg', 'jpeg'}
    screenshots = glob.glob('%s/%s*' % (config['rec_path'], config['rec_prefix']))
    screenshots = [screenshot for screenshot in screenshots if screenshot.split('.')[-1] in screenshot_filetypes]
    if len(screenshots) == 0:
        return None
    screenshots.sort()
    return screenshots[-1]

if minutes_since_last_tweet() >= config['twitter']['interval']:
    twitch_set_status(grammar.flatten("#twitch_status#"))
    twitch_set_communities(twitch_communities)
    tweet('#first_tweet#')
    discord('#chat_msg#')

try:
    while True:
        time.sleep(10)
        if minutes_since_last_tweet() >= config['twitter']['interval']:
            tweet('#periodic_tweet#', get_last_screenshot())
except KeyboardInterrupt as e:
    pass

