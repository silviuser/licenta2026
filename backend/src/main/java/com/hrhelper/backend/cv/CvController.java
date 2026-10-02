package com.hrhelper.backend.cv;

import com.hrhelper.backend.common.PageResponse;
import com.hrhelper.backend.cv.dto.CvBulkUploadResponse;
import com.hrhelper.backend.cv.dto.CvEmailUpdateRequest;
import com.hrhelper.backend.cv.dto.CvResponse;
import com.hrhelper.backend.security.CurrentUser;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/cvs")
public class CvController {

    private final CvService cvService;

    public CvController(CvService cvService) {
        this.cvService = cvService;
    }

    /**
     * Bulk upload (REWORK 1 D21): 1..N PDFs in the {@code files} field, optional
     * {@code jdId} to also create applications. Returns 202 immediately with
     * per-file statuses; extraction runs in the background.
     */
    @PostMapping
    public ResponseEntity<CvBulkUploadResponse> upload(
            @RequestParam("files") List<MultipartFile> files,
            @RequestParam(value = "jdId", required = false) UUID jdId) {
        CvBulkUploadResponse body = cvService.uploadBatch(CurrentUser.id(), files, jdId);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(body);
    }

    @GetMapping
    public PageResponse<CvResponse> list(Pageable pageable) {
        return PageResponse.from(
                cvService.list(CurrentUser.id(), pageable).map(CvResponse::from));
    }

    @GetMapping("/{id}")
    public CvResponse get(@PathVariable UUID id) {
        return CvResponse.from(cvService.get(CurrentUser.id(), id));
    }

    @GetMapping("/{id}/file")
    public ResponseEntity<Resource> download(@PathVariable UUID id) {
        Cv cv = cvService.get(CurrentUser.id(), id);
        Resource body = new ByteArrayResource(cv.getPdfData());
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"" + cv.getOriginalFilename() + "\"")
                .contentLength(cv.getSizeBytes())
                .body(body);
    }

    /** Set/clear the recruiter's manual email override (REWORK 4 D45). */
    @PatchMapping("/{id}/email")
    public CvResponse updateEmail(
            @PathVariable UUID id, @Valid @RequestBody CvEmailUpdateRequest request) {
        return CvResponse.from(cvService.updateEmail(CurrentUser.id(), id, request.manualEmail()));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable UUID id) {
        cvService.delete(CurrentUser.id(), id);
        return ResponseEntity.noContent().build();
    }
}
