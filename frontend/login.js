/*
this is the portal to connect to the Lucid system via the API route
login:
- userID and password will be used to authenticate the user for the session system via the API route, using the Master server database
- nodeUserID and password will be used to authenticate the NodeUser for the session system via the API route, using the master server database
- the login will return the corrisponding error message if the login is unsuccessful
- the login will return the corrisponding IDToken for the user and the NodeUser if the login is successful
- the IDToken will be used to authenticate the user and the NodeUser for the session system via the API route
- the IDToken will be used to authenticate the user and the NodeUser for the blockchain system and the LucidLedger system via the API route

schema:
modern and clean with a focus on user experience and ease of use
UserID and password will be used to authenticate the user for the session system via the API route, using the Master server database, or the NodeUser database
the login will return the corrisponding error message if the login is unsuccessful
the login will return the corrisponding IDToken for the user and the NodeUser if the login is successful
the IDToken will be used to authenticate the user and the NodeUser for the session system via the API route
the IDToken will be used to authenticate the user and the NodeUser for the blockchain system and the LucidLedger system via the API route
the login will have a remember me option to store the IDToken in the browser's local storage
the login will have a forgot password option to reset the password
the login will have a register option to create a new account
the login will have a login with Google option to login with a Google account
on successful login, the user will be redirected to the dashboard page (dashboard.js)


*/