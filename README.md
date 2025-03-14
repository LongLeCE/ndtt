# 1. Disclaimer
**If you are not within my friend group, you probably shouldn't care about this repo**

# 2. Dependencies
`pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib`

# 3. Credentials
You will need an account with Google Sheets API, Google Slides API and Google Youtube Data API access enabled and OAuth2 configured. Alternatively, become my friend and get the `credentials.json` from me :))

# 4. How to run
`python main.py -h` should give you all the options

If you are still clueless, the command should look something like `python main.py -n ndtt_test -u urls.csv -d 30 -l 8 -s`

Upon first launch/whenever credentials expire, a browser tab will open up and ask you to sign in into your Google account. Give all the permissions asked. Remember the account I mentioned above? Use it, especially if you don't want to use your main account.

# 5. FAQs
`It used to run just fine but now I'm getting credentials error upon running the script`
Try removing the generated `token.json` and run again