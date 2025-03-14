import os
from random import shuffle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from argparse import ArgumentParser
from urllib.parse import urlparse, parse_qs
from functools import cache
import math
import csv

# If modifying these scopes, delete the file token.json.
SCOPES = [
	'https://www.googleapis.com/auth/presentations',
	'https://www.googleapis.com/auth/spreadsheets',
	'https://www.googleapis.com/auth/youtube.force-ssl'
]


def build_parser():
	parser = ArgumentParser()
	parser.add_argument('--name', '-n', required=True, help='name of presentation')
	parser.add_argument('--urls', '-u', required=True, help='path to csv file containing the urls')
	parser.add_argument('--host', '-ho', help='name of host (will subtract 1 from total number of players for score formula if host found in player list)')
	parser.add_argument('--duration', '-d', type=int, default=0, help='duration of playback in seconds, 0 means unlimited, default = 0')
	parser.add_argument('--fillers', '-f', type=int, default=0, help='number of filler slides to prepend at the beginning (to avoid peeking), default = 0')
	parser.add_argument('--rows', '-r', type=int, default=3, help='number of rows of videos per slide, default = 3')
	parser.add_argument('--cols', '-c', type=int, default=3, help='number of cols of videos per slide, default = 3')
	parser.add_argument('--limit', '-l', type=int, default=9, help='max number of videos per slide, if less than rows * cols desired, default = 9 (3x3)')
	parser.add_argument('--width', '-wr', type=float, default=0.3, help='ratio between a single video width and slide width, default = 0.3')
	parser.add_argument('--height', '-hr', type=float, default=0.3, help='ratio between a single video height and slide height, default = 0.3')
	parser.add_argument('--shuffle', '-s', action='store_true', help='shuffles the given url list')
	return parser


def build_gservices():
	# The file token.json stores the user's access and refresh tokens, and is
	# created automatically when the authorization flow completes for the first
	# time.
	if os.path.exists('token.json'):
		creds = Credentials.from_authorized_user_file('token.json', scopes=SCOPES)
	else:
		creds = None

	# If there are no (valid) credentials available, let the user log in.
	if not creds or not creds.valid:
		if creds and creds.expired and creds.refresh_token:
			creds.refresh(Request())
		else:
			flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
			creds = flow.run_local_server(port=0)

		# Save the credentials for the next run
		with open('token.json', 'w+') as f:
			f.write(creds.to_json())

	return {
		'slides': build('slides', 'v1', credentials=creds),
		'sheets': build('sheets', 'v4', credentials=creds),
		'youtube': build('youtube', 'v3', credentials=creds)
	}


def get_presentation(service, presentation_id):
	return service.presentations().get(presentationId=presentation_id).execute()


def get_spreadsheet(service, spreadsheet_id):
	return service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()


def create_slides(service, presentation_id, layout='BLANK', n=1, idx=None):
	requests = [
		{
            'createSlide': {
                'insertionIndex': idx,
                'slideLayoutReference': {
                    'predefinedLayout': layout
                }
            }
        } for _ in range(n)
	]
	ret = service.presentations().batchUpdate(presentationId=presentation_id, body={'requests': requests}).execute()
	return [reply['createSlide']['objectId'] for reply in ret['replies']]


def filler_slides(service, presentation_id, n=1, idx=None):
	if n == 0:
		return
	create_slides(service, presentation_id, layout='TITLE', n=n, idx=idx)
	presentation = get_presentation(service, presentation_id)
	start_idx = idx if idx is not None else len(presentation['slides']) - n
	requests = []
	for i in range(start_idx, start_idx + n):
		requests.extend([
			{
				'insertText': {
					'objectId': presentation['slides'][i]['pageElements'][0]['objectId'],
					'text': 'Filler'
				}
			},
			{
				'deleteObject': {
					'objectId': presentation['slides'][i]['pageElements'][1]['objectId']
				}
			}
		])
	service.presentations().batchUpdate(presentationId=presentation_id, body={'requests': requests}).execute()


def extract_params_from_youtube_url(url):
	parsed = urlparse(url)
	params = parse_qs(parsed.query)
	if 'v' not in params:  # youtu.be, also WHY?
		params['v'] = [parsed.path.lstrip('/')]
	return params


def video_slides(service, presentation_id, video_ids, duration=0, rows=3, cols=3, w_r=0.3, h_r=0.3, limit_per_page=None, idx=None):
	num_vids_per_slide = rows * cols
	if limit_per_page is not None:
		num_vids_per_slide = min(num_vids_per_slide, limit_per_page)
	num_slides = math.ceil(len(urls) / num_vids_per_slide)
	slide_ids = create_slides(service, presentation_id, layout='BLANK', n=num_slides, idx=idx)
	presentation = get_presentation(service, presentation_id)
	slide_w = presentation['pageSize']['width']['magnitude']
	slide_h = presentation['pageSize']['height']['magnitude']
	unit = presentation['pageSize']['width']['unit']
	video_w = min(1 / cols, w_r) * slide_w
	video_h = min(1 / rows, h_r) * slide_h
	video_block_x = max((slide_w - video_w * cols) / 2, 0)
	video_block_y = max((slide_h - video_h * rows) / 2, 0)
	params = [extract_params_from_youtube_url(url[1]) for url in urls]
	requests = []
	for i in range(len(urls)):
		requests.append({
			'createVideo': {
				'id': params[i]['v'][0],
				'source': 'YOUTUBE',
				'elementProperties': {
					'pageObjectId': slide_ids[i // num_vids_per_slide],
					'size': {
						'width': {
							'magnitude': video_w,
							'unit': unit
						},
						'height': {
							'magnitude': video_h,
							'unit': unit
						}
					},
					'transform': {
						'scaleX': 1,
						'scaleY': 1,
						'translateX': (i % num_vids_per_slide % cols) * video_w + video_block_x,
						'translateY': ((i % num_vids_per_slide) // rows) * video_h + video_block_y,
						'unit': unit
					}
				}
			}
		})
	ret = service.presentations().batchUpdate(presentationId=presentation_id, body={'requests': requests}).execute()
	requests = []
	for i in range(len(urls)):
		t = params[i].get('t')
		if duration > 0 or t is not None:
			t = 0 if t is None else int(t[0].rstrip('s'))
			requests.append({
				'updateVideoProperties': {
					'objectId': ret['replies'][i]['createVideo']['objectId'],
					'videoProperties': {
						'start': t,
						'end': t + duration if duration > 0 else None
					},
					'fields': '*'
				}
			})
	if requests:
		service.presentations().batchUpdate(presentationId=presentation_id, body={'requests': requests}).execute()


def create_presentation(service, name=None):
	presentation = service.presentations().create(body={'title': name}).execute()
	presentation_id = presentation['presentationId']
	requests = [
		{
			'deleteObject': {
				'objectId': presentation['slides'][0]['objectId']
			}
		}
	]
	service.presentations().batchUpdate(presentationId=presentation_id, body={'requests': requests}).execute()
	return presentation_id


def create_spreadsheet(service, name=None):
	spreadsheet = service.spreadsheets().create(body={'properties': {'title': name}}, fields='spreadsheetId').execute()
	spreadsheet_id = spreadsheet['spreadsheetId']
	return spreadsheet_id


def create_sheets(service, spreadsheet_id, names=[], idx=None):
	requests = []
	for i, name in enumerate(names):
		requests.append({
			'addSheet': {
				'properties': {
					'title': name,
					'index': None if idx is None else idx + i
				}
			}
		})
	if requests:
		ret = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': requests}).execute()
		return [reply['addSheet']['properties']['sheetId'] for reply in ret['replies']]
	return []


def delete_sheet(service, spreadsheet_id, idx=None):
	spreadsheet = get_spreadsheet(service, spreadsheet_id)
	idx = idx if idx is not None else len(spreadsheet['sheets']) - 1
	requests = [
		{
			'deleteSheet': {
				'sheetId': spreadsheet['sheets'][idx]['properties']['sheetId']
			}
		}
	]
	service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': requests}).execute()


@cache
def num2col(n):
	col = ''
	while n > 0:
		n -= 1
		col = f'{chr(n % 26 + 65)}{col}'
		n //= 26
	return col


def populate_spreadsheet(service, spreadsheet_id, urls, host=None):
	players = sorted({url[0] for url in urls})
	num_players = len(players)
	is_host_in_player_list = host in players
	last_player_col = num2col(num_players)
	num_songs = len(urls)
	data = [
		# Guess
		{
			'range': f'Guess!A1:{last_player_col}1',
			'values': [players]
		},
		{
			'range': f'Guess!A{num_songs + 2}:{last_player_col}{num_songs + 2}',
			'values': [
				[f'=COUNTIF($A$2:${last_player_col}${num_songs + 1},{num2col(i)}1)' for i in range(1, num_players + 1)]
			]
		},
		# Total
		{
			'range': f'Total!A1:{last_player_col}2',
			'values': [
				players,
				[f'=Round!{num2col(i)}2' for i in range(1, num_players + 1)]
			]
		},
		# Round
		{
			'range': f'Round!A1:{last_player_col}{num_songs + 2}',
			'values': [
				players,
				[f'=SUM({num2col(i)}3:{num2col(i)}{num_songs + 2})' for i in range(1, num_players + 1)],
				*[
					[
						f'=IF({num2col(i)}$1<>${num2col(num_players + 1)}{j},COUNTIF(Guess!{num2col(i)}{j - 1},${num2col(num_players + 1)}{j}), IF(COUNTIF(Guess!$A{j - 1}:${num2col(num_players)}{j - 1},${num2col(num_players + 1)}{j})-COUNTIF(Guess!{num2col(i)}{j - 1},${num2col(num_players + 1)}{j})=${num2col(num_players + 2)}$2-1,-2,COUNTIF(Guess!$A{j - 1}:${num2col(num_players)}{j - 1},${num2col(num_players + 1)}{j})-COUNTIF(Guess!{num2col(i)}{j - 1},${num2col(num_players + 1)}{j})))' for i in range(1, num_players + 1)
					] for j in range(3, num_songs + 3)
				]
			]
		},
		{
			'range': f'Round!{num2col(num_players + 2)}1:{num2col(num_players + 2)}2',
			'values': [
				['Number of players'],
				[num_players - 1 if is_host_in_player_list else num_players]
			]
		},
		{
			'range': f'Round!{num2col(num_players + 1)}3:{num2col(num_players + 2)}{num_songs + 2}',
			'values': urls
		}
	]
	service.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body={'valueInputOption': 'USER_ENTERED', 'data': data}).execute()


def create_playlist(service, title, description=None, privacy_status='public'):
	request_body = {
		'snippet': {
			'title': title
		},
		'status': {
			'privacyStatus': privacy_status
		}
	}
	if description:
		request_body['snippet']['description'] = description
	playlist = service.playlists().insert(
		part='id,snippet,status',
		body=request_body
	).execute()
	playlist_id = playlist['id']
	return playlist_id


def populate_playlist(service, playlist_id, video_ids):
	for video_id in video_ids:
		service.playlistItems().insert(
            part='snippet',
            body={
                'snippet': {
                    'playlistId': playlist_id,
                    'resourceId': {
                        'kind': 'youtube#video',
                        'videoId': video_id
                    }
                }
            }
        ).execute()


def main(args):
	try:
		urls = []
		with open(args.urls, newline='') as f:
			# urls = f.read().split('\n')
			for row in csv.reader(f):
				urls.append(row)
		if args.shuffle:
			shuffle(urls)
		video_ids = map(lambda x: extract_params_from_youtube_url(x[1])['v'][0], urls)

		services = build_gservices()
		slide_service = services['slides']
		sheets_service = services['sheets']
		youtube_service = services['youtube']

		print('Creating presentation...')
		presentation_id = create_presentation(slide_service, name=args.name)
		filler_slides(slide_service, presentation_id, n=args.fillers)
		video_slides(slide_service, presentation_id, video_ids, duration=args.duration, rows=args.rows, cols=args.cols, w_r=args.width, h_r=args.height, limit_per_page=args.limit)
		print(f'Presentation URL: https://docs.google.com/presentation/d/{presentation_id}\nDone')

		print('Creating spreadsheet...')
		spreadsheet_id = create_spreadsheet(sheets_service, name=args.name)
		create_sheets(sheets_service, spreadsheet_id, ['Guess', 'Total', 'Round'])
		delete_sheet(sheets_service, spreadsheet_id, 0)
		populate_spreadsheet(sheets_service, spreadsheet_id, urls, host=args.host)
		print(f'Spreadsheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}\nDone')

		print('Creating playlist...')
		playlist_id = create_playlist(youtube_service, args.name)
		populate_playlist(youtube_service, playlist_id, video_ids)
		print(f'Playlist URL: https://www.youtube.com/playlist?list={playlist_id}\nDone')
	except HttpError as err:
		print(err)
	else:
		print('ok')


if __name__ == '__main__':
	parser = build_parser()
	args = parser.parse_args()
	main(args)
