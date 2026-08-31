/* 
this is the interface used to create a new sessionID and to find a peer to peer remote desktop sharing session
find-peer:
- uses the SessionID to find a peer to peer remote desktop sharing session
- the session connection will be established via the API route
create new sessionID:
- the new sessionID will be created using a sha512 hash function to produce a 10 digit session id consisting of 0-9 and a-z
- the new sessionID will be stored in the node-operation-database and the master server database
- the new sessionID will be returned to the user via the API route
- the new sessionID will be used to find a peer to peer remote desktop sharing session
- the new sessionID will be used to create a new session connections via the API route
*/