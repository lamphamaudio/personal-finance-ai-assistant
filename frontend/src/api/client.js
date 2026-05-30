/**
 * Centralized API Fetch Client wrapper.
 */
class ApiClient {
  async request(endpoint, options = {}) {
    const url = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    
    // Set headers
    const headers = new Headers(options.headers || {});
    if (!(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }
    
    const config = {
      ...options,
      headers
    };
    
    try {
      const response = await fetch(url, config);
      
      // If response is text stream or event stream, return raw response
      if (response.headers.get('Content-Type')?.includes('text/event-stream')) {
        return response;
      }
      
      let data = null;
      const contentType = response.headers.get('Content-Type') || '';
      if (contentType.includes('application/json')) {
        data = await response.json();
      } else {
        data = await response.text();
      }
      
      if (!response.ok) {
        const errorMessage = data && typeof data === 'object' && data.error 
          ? data.error 
          : `API Error: ${response.status} ${response.statusText}`;
        throw new Error(errorMessage);
      }
      
      return data;
    } catch (error) {
      console.error(`API Request Failure [${options.method || 'GET'} ${url}]:`, error);
      throw error;
    }
  }

  get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' });
  }

  post(endpoint, body, options = {}) {
    return this.request(endpoint, { 
      ...options, 
      method: 'POST', 
      body: body instanceof FormData ? body : JSON.stringify(body) 
    });
  }

  patch(endpoint, body, options = {}) {
    return this.request(endpoint, { 
      ...options, 
      method: 'PATCH', 
      body: body instanceof FormData ? body : JSON.stringify(body) 
    });
  }

  delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' });
  }
}

export const api = new ApiClient();
