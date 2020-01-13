#  BSD 3-Clause License
#
#  Copyright (c) 2020, Elasticsearch BV
#  All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are met:
#
#  * Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
#  * Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
#  * Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#  DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
#  FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
#  DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#  SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
#  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#  OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import time
from typing import Dict, Tuple, Any

import fastapi
from starlette.datastructures import URL
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

import elasticapm
from elasticapm.utils import compat, get_url_dict
from elasticapm import Client
from elasticapm.utils.disttracing import TraceParent


class ElasticAPM(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, config=None, instrument=True):
        super().__init__(app)
        config = config or {}
        config.setdefault("framework_name", "fastapi")
        config.setdefault("framework_version", fastapi.__version__)
        self.client = Client(config=config)

        if instrument:
            elasticapm.instrument()

        app.middleware("http")(self.dispatch)

    def get_data_from_request(self, request: Request) -> Dict[str, Any]:
        data = {"headers": dict(request.headers.items()),
                "method": request.method,
                "socket": {
                    "remote_address": request.client.host,
                    "encrypted": request.url.scheme == "https",
                },
                "cookies": dict(**request.cookies),
                "url": get_url_dict(str(request.url))
                }
        return data

    def get_data_from_response(self, response: Response) -> Dict[str, Any]:
        data = {"status_code": response.status_code}
        if response.headers:
            data["headers"] = dict(response.headers.items())
        return data

    def get_matched_route(self, request: Request):
        matched_route = [route for route in request.scope['router'].routes
                         if route.endpoint == request.scope['endpoint']][0].path
        return matched_route

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        start_time = time.time()

        self.client.begin_transaction("request")
        response = await call_next(request)

        transaction_name = self.get_matched_route(request)
        transaction_name = " ".join((request.method, transaction_name)) \
            if transaction_name else ""
        transaction_result = str(response.status_code)[0] + "xx"

        elasticapm.set_context(lambda: self.get_data_from_request(request), "request")
        elasticapm.set_context(lambda: self.get_data_from_response(response),
                               "response")
        self.client.end_transaction(transaction_name, transaction_result)
        process_time = time.time() - start_time
        print(str(process_time))

        return response
