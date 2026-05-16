ISSUES_SEARCH_QUERY = """
query SearchIssues($query: String!, $first: Int!, $after: String) {
  rateLimit {
    limit
    remaining
    resetAt
    cost
  }
  search(type: ISSUE, query: $query, first: $first, after: $after) {
    issueCount
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      __typename
      ... on Issue {
        id
        number
        title
        bodyText
        url
        state
        stateReason
        createdAt
        updatedAt
        closedAt
        comments {
          totalCount
        }
        repository {
          name
          nameWithOwner
          url
          isPrivate
          owner {
            login
          }
        }
        author {
          login
          url
          avatarUrl
        }
        assignees(first: 10) {
          nodes {
            login
            url
            avatarUrl
          }
        }
        labels(first: 30) {
          nodes {
            name
            color
            description
          }
        }
        milestone {
          title
          dueOn
          state
        }
      }
    }
  }
}
"""


PULL_REQUESTS_SEARCH_QUERY = """
query SearchPullRequests($query: String!, $first: Int!, $after: String) {
  rateLimit {
    limit
    remaining
    resetAt
    cost
  }
  search(type: ISSUE, query: $query, first: $first, after: $after) {
    issueCount
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      __typename
      ... on PullRequest {
        id
        number
        title
        bodyText
        url
        state
        isDraft
        merged
        mergedAt
        reviewDecision
        createdAt
        updatedAt
        closedAt
        headRefName
        baseRefName
        repository {
          name
          nameWithOwner
          url
          isPrivate
          owner {
            login
          }
        }
        author {
          login
          url
          avatarUrl
        }
        assignees(first: 10) {
          nodes {
            login
            url
            avatarUrl
          }
        }
        labels(first: 30) {
          nodes {
            name
            color
            description
          }
        }
        reviewRequests(first: 20) {
          nodes {
            requestedReviewer {
              __typename
              ... on User {
                login
              }
              ... on Team {
                name
                slug
              }
            }
          }
        }
        reviews(last: 20) {
          nodes {
            state
            submittedAt
            author {
              login
            }
          }
        }
        closingIssuesReferences(first: 20) {
          nodes {
            number
            title
            url
            state
            repository {
              nameWithOwner
            }
          }
        }
        commits(last: 1) {
          nodes {
            commit {
              oid
              abbreviatedOid
              statusCheckRollup {
                state
                contexts(first: 50) {
                  nodes {
                    __typename
                    ... on CheckRun {
                      name
                      status
                      conclusion
                      detailsUrl
                    }
                    ... on StatusContext {
                      context
                      state
                      targetUrl
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


VIEWER_QUERY = """
query Viewer($first: Int!) {
  viewer {
    login
    name
    avatarUrl
    url
    organizations(first: $first) {
      nodes {
        login
        name
        url
        avatarUrl
        repositories {
          totalCount
        }
      }
    }
  }
}
"""
