package com.hrhelper.backend.apply.dto;

/**
 * The only JD data exposed publicly (REWORK 3 D35): title + description. No
 * internal ids, recruiter identity, or other candidates' data.
 */
public record PublicJobView(String jobTitle, String jobDescription) {}
