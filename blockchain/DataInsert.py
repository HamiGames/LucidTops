""" the protocol for how the data from the compressed session record is added to the next block in the blockchain system 
limitations:
- the first 100 comressed session records are added to the next block in the blockchain system
- each session record generates a session key to view the compressed session record
- a session key is valid for 2 years after the session record is added to the blockchain system
- the session key only allows access to the userID involved in the session record
- a copy of the session key is added to the blockchain within the created block
- the total size of a block is limited to 1MB

requirements:
- the session record must be in a compressed state
- the session record must be in a valid state
- the session record must be in a unique state
- the session record must be in the correct format
- the session record must be in the correct location (the compressed database) 

"""