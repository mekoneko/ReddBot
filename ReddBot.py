__author__ = 'mekoneko'

import time
import praw
import json
import os
from random import choice
from twython import Twython

watched_subreddit = 'all'
results_limit = 200
results_limit_comm = 1000
bot_agent_names = ['Reddit words 0.5', 'reddit topic collector 0.5', 'redditlink bot v12']
loop_timer = 60
secondary_timer = 600
buffer_reset_lenght = 2000
DEBUG_LEVEL = 1


class ConnectSocialMedia:

    def __init__(self, authinfo, useragent):

        self.reddit_session = self.connect_to_reddit(authinfo, useragent=useragent)
        self.twitter_session = self.connect_to_twitter(authinfo)

    @staticmethod
    def connect_to_reddit(authinfo, useragent):
        try:
            r = praw.Reddit(user_agent=useragent, api_request_delay=1)
            r.login(authinfo['REDDIT_BOT_USERNAME'], authinfo['REDDIT_BOT_PASSWORD'])
        except:
            print('ERROR: Cant login to Reddit.com')
        return r

    @staticmethod
    def connect_to_twitter(authinfo):
        try:
            t = Twython(authinfo['APP_KEY'], authinfo['APP_SECRET'],
                        authinfo['OAUTH_TOKEN'], authinfo['OAUTH_TOKEN_SECRET'])
        except:
            print('ERROR: Cant authenticate into twitter')
        return t


class ReadConfigFiles:
    def __init__(self):
        self.data_modified_time = 0

    def readauthfile(self, authfilename):
        with open(authfilename, 'r', encoding='utf-8') as f:
            bot_auth_info = json.load(f)
        return bot_auth_info

    def readdatafile(self, datafilename):
        self.data_modified_time = os.stat(datafilename).st_mtime
        with open(datafilename, 'r', encoding='utf-8') as f:
            redd_data = json.load(f)
            redd_data['KEYWORDS'] = sorted(redd_data['KEYWORDS'], key=len, reverse=True)
            redd_data['SRSs'] = [x.lower() for x in redd_data['SRSs']]
        return redd_data


class ReddBot:

    def __init__(self, useragent, authfilename, datafilename):
        self.args = {'useragent': useragent, 'authfilename': authfilename, 'datafilename': datafilename}
        self.pulllimit = {'submissions': results_limit, 'comments': results_limit_comm}
        self.first_run = True
        self.cont_num = {'comments': 0, 'submissions': 0}
        self.already_done = {'comments': [], 'submissions': []}
        self.loops = ['submissions']  # 'submissions' and 'comments' loops
        self.permcounters = {'comments': 0, 'submissions': 0}
        self.loop_counter = 0
        self.redd_data = {}
        self.bot_auth_info = {}
        self.reddit_session = None
        self.twitter = None
        self.config = ReadConfigFiles()

        while True:
            self.loop_counter += 1
            if self.loop_counter >= secondary_timer / loop_timer:
                self.debug('SEDONDARY LOOP')
                self.loop_counter = 0
            self._mainlooper()

    def _mainlooper(self):
        #try:
        if os.stat(self.args['datafilename']).st_mtime > self.config.data_modified_time:  # check if config file has changed
            self.redd_data = self.config.readdatafile(self.args['datafilename'])
            self.bot_auth_info = self.config.readauthfile(self.args['authfilename'])
            bot_session = ConnectSocialMedia(self.bot_auth_info, useragent=self.args['useragent'])
            self.reddit_session = bot_session.reddit_session
            self.twitter = bot_session.twitter_session
            self.debug('CONFIG FILES REREAD, RECONNEECTED!')

        self.cont_num['submissions'], self.cont_num['comments'] = 0, 0

        for loop in self.loops:
            self.contentloop(target=loop)
            if len(self.already_done[loop]) >= buffer_reset_lenght:
                self.already_done[loop] = self.already_done[loop][int(len(self.already_done[loop]) / 2):]
                self.debug('DEBUG:buffers LENGHT after trim {0}'.format(len(self.already_done[loop])))
            if not self.first_run:
                self.pulllimit[loop] = self._calculate_pull_limit(self.cont_num[loop], target=loop)
            self.permcounters[loop] += self.cont_num[loop]

        self.debug('Running for :{0} secs. Submissions so far: {1}, THIS run: {2}.'
                   ' Comments so  far:{3}, THIS run:{4}'
                   .format(int((time.time() - start_time)), self.permcounters['submissions'],
                           self.cont_num['submissions'], self.permcounters['comments'],
                           self.cont_num['comments']))

        self.first_run = False

        self.debug(self.pulllimit['submissions'])
        self.debug(self.pulllimit['comments'])
        #except:
            #print('General Error')

        time.sleep(loop_timer)

    def _calculate_pull_limit(self, lastpullnum, target):
        """this needs to be done better"""
        add_more = {'submissions': 80, 'comments': 300}   # how many items above last pull number to pull next run

        if not lastpullnum:
            lastpullnum = self.pulllimit[target] - 1   # in case no new results are returned

        res_diff = self.pulllimit[target] - lastpullnum
        if res_diff == 0:
            self.pulllimit[target] *= 2
        else:
            self.pulllimit[target] = lastpullnum + add_more[target]
        return int(self.pulllimit[target])

    def contentloop(self, target):
        try:
            if target == 'submissions':
                results = self.reddit_session.get_subreddit(watched_subreddit).get_new(limit=self.pulllimit[target])
            if target == 'comments':
                results = self.reddit_session.get_comments(watched_subreddit, limit=self.pulllimit[target])
        except:
            print('ERROR: Cant connect to reddit, may be down.')
        try:
            for content in results:
                if content.id not in self.already_done[target]:
                    for manip in self.mastermanipulator(target=target):
                        return_text = manip(content)
                        if return_text is not False:
                            print(return_text)
                    self.already_done[target].append(content.id)  # add to list of already processed submissions
                    self.cont_num[target] += 1   # count the number of submissions processed each run
        except:
            print('content loop error')

    @staticmethod
    def debug(debugtext, level=DEBUG_LEVEL):
        if level >= 1:
            print('*DEBUG: {}'.format(debugtext))

    def mastermanipulator(self, target):

        def topicmessanger(dsubmission):
            if target == 'submissions':
                op_text = dsubmission.title + dsubmission.selftext
            if target == 'comments':
                op_text = dsubmission.body

            for item in self.redd_data['KEYWORDS']:
                if item.lower() in op_text.lower():
                    if target == 'comments':
                        msg = "Comment concerning #{0} posted in /r/{1} {2} #reddit"\
                            .format(item, dsubmission.subreddit, dsubmission.permalink)

                    elif target == 'submissions':
                        subreddit = str(dsubmission.subreddit)
                        if subreddit.lower() in self.redd_data['SRSs'] and 'reddit.com' in dsubmission.url and not dsubmission.is_self:
                            msg = 'ATTENTION: possible reactionary brigade from /r/{1} regarding #{0}: {2} #reddit'\
                                .format(item, dsubmission.subreddit, dsubmission.short_link)
                            try:
                                s = self.reddit_session.get_submission(dsubmission.url)
                                s.comments[0].reply('##NOTICE: *This comment/thread has just been targeted'
                                                    ' by a downvote brigade from [/r/{0}]({1})* \n\n '
                                                    '*I am a bot, please PM if this message is a mistake.* \n\n'
                                                    .format(dsubmission.subreddit, dsubmission.short_link))
                            except:
                                print('brigade warning failed, cant comment')
                        else:
                            msg = 'Submission regarding #{0} posted in /r/{1} : {2} #reddit'.format(
                                item, dsubmission.subreddit, dsubmission.short_link)
                    if len(msg) > 140:
                        msg = msg[:-8]
                        self.debug('MSG exceeding 140 characters!!')
                    #self.reddit_session.send_message(bot_auth_info['REDDIT_PM_TO'], 'New {0} discussion!'.format(item), msg)
                    try:
                        self.twitter.update_status(status=msg)
                    except:
                        print('ERROR: couldnt update twitter status')

                    return 'New Topic match in:{0}, keyword:{1}'.format(dsubmission.subreddit, item)
            return False

        def nothing(nothing):
            return False

        '''
        IF YOU WANT TO DISABLE A BOT FEATURE for a specific loop REMOVE IT FROM THE DICTIONARY BELLOW
        '''
        returnfunctions = {'comments': [topicmessanger, nothing], 'submissions': [topicmessanger, nothing]}
        return returnfunctions[target]

start_time = time.time()
bot1 = ReddBot(useragent=choice(bot_agent_names), authfilename='ReddAUTH.json', datafilename='ReddData.json')
