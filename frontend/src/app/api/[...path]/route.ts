import { NextRequest, NextResponse } from 'next/server';

const API_BACKEND = process.env.API_BACKEND_URL || 'http://skuld-api:8000';

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function PUT(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path);
}

async function proxy(request: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join('/');
  const url = new URL(request.url);
  const targetUrl = `${API_BACKEND}/api/${path}${url.search}`;

  const headers = new Headers();
  // Forward auth header
  const auth = request.headers.get('authorization');
  if (auth) headers.set('authorization', auth);
  headers.set('content-type', request.headers.get('content-type') || 'application/json');

  const fetchOptions: RequestInit = {
    method: request.method,
    headers,
  };

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    fetchOptions.body = await request.text();
  }

  try {
    const response = await fetch(targetUrl, fetchOptions);
    const data = await response.text();

    return new NextResponse(data, {
      status: response.status,
      headers: {
        'content-type': response.headers.get('content-type') || 'application/json',
      },
    });
  } catch (error) {
    return NextResponse.json(
      { detail: 'Backend unavailable', error: String(error) },
      { status: 502 }
    );
  }
}
