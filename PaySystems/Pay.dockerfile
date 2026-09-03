# this is the dockerfile to create the payment system container for the LucidTops system.
# this is a purely internal network based payment system container for the LucidTops system.
# only the master server and the AdminUser will have access to the payment system container.
# this container will be useable via the API routes.(uvicorn, FastAPI)
# payment systems will route from the TOR Hosted server through Clearnet operations Via API routes.
