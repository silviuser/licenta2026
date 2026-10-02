import { http, HttpResponse } from 'msw';
import type { Page, UserResponse } from '../../api/types';
import { application1, cv1, dashboard, jd1, succeededJob } from './fixtures';

export const BASE = 'http://localhost:8080';

const user: UserResponse = {
  id: 'u-1',
  email: 'recruiter@example.com',
  fullName: 'Test Recruiter',
  role: 'RECRUITER',
  enabled: true,
};

function page<T>(content: T[]): Page<T> {
  return {
    content,
    totalElements: content.length,
    totalPages: 1,
    number: 0,
    size: 20,
  };
}

/** Default happy-path handlers; individual tests override with server.use(). */
export const handlers = [
  http.post(`${BASE}/api/auth/login`, () =>
    HttpResponse.json({ accessToken: 'test-token', expiresIn: 7200, role: 'RECRUITER' }),
  ),
  http.post(`${BASE}/api/auth/register`, () => HttpResponse.json(user, { status: 201 })),
  http.get(`${BASE}/api/auth/me`, () => HttpResponse.json(user)),

  http.get(`${BASE}/api/dashboard`, () => HttpResponse.json(dashboard)),

  http.get(`${BASE}/api/cvs`, () => HttpResponse.json(page([cv1]))),
  http.get(`${BASE}/api/jds`, () => HttpResponse.json(page([jd1]))),
  http.get(`${BASE}/api/jds/:id`, () => HttpResponse.json(jd1)),
  http.get(`${BASE}/api/jds/:id/applications`, () => HttpResponse.json([application1])),
  http.get(`${BASE}/api/jds/:id/apply-link`, () =>
    HttpResponse.json({ exists: false, enabled: false, url: null }),
  ),
  http.get(`${BASE}/api/matches`, () => HttpResponse.json(page([succeededJob('job-1')]))),

  http.get(`${BASE}/api/matches/:jobId`, ({ params }) =>
    HttpResponse.json(succeededJob(String(params.jobId))),
  ),

  http.get(`${BASE}/api/nlp/info`, () =>
    HttpResponse.json({ pipeline_version: 'skill_matcher@test', placeholder_caveat: 'Encoder is a placeholder.' }),
  ),
];
