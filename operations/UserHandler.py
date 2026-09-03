""" this is the UserHandler for the LucidTops system, used by the NodeUser for existing UserID's in the UserDB
operations:
- accepts if a UserID and correct IDToken for the UserID is provided
- allows the UserID access to the Sessions system via the API routes (FastAPI)
- allows the UserID access to the Operations system via the API routes (FastAPI)(selected operations only)
- allows the UserID access to the PaySystems system via the API routes (FastAPI)(incoming payments only)
- allows the UserID access to the Blockchain system via the API routes (FastAPI)(ledger operations only)
- is accessed via the Frontend (javascript) via the API routes (FastAPI)
"""