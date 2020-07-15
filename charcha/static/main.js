function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

$('.upvote-button').click(function(){
    //the button that was clicked (upvote or downvote)
    var elem = $(this);
    var score = elem.find(".score");
    var objectType = elem.data("object-type");
    var objectId = elem.data("object-id");
    
    var url = "/api/" + objectType + "/" + objectId + "/upvote";
    
    var csrftoken = getCookie('csrftoken');
    $.post(url, {'csrfmiddlewaretoken': csrftoken })
        .done(function(data){
          score.html(data);
        })
        .fail(function(data){
          score.html('?');
        });
});


(function() {
    var uploadUrl = "/api/upload";
    
    addEventListener("trix-attachment-add", function(event) {
      if (event.attachment.file) {
        uploadFileAttachment(event.attachment)
      }
    })
  
    function uploadFileAttachment(attachment) {
      uploadFile(attachment.file, setProgress, setAttributes)
  
      function setProgress(progress) {
        attachment.setUploadProgress(progress)
      }
  
      function setAttributes(attributes) {
        attachment.setAttributes(attributes)
      }
    }
  
    function uploadFile(file, progressCallback, successCallback) {
      var key = createStorageKey(file)
      var formData = createFormData(key, file)
      var xhr = new XMLHttpRequest()
  
      xhr.open("POST", uploadUrl, true)
  
      xhr.upload.addEventListener("progress", function(event) {
        var progress = event.loaded / event.total * 100
        progressCallback(progress)
      })
  
      xhr.addEventListener("load", function(event) {
        if (xhr.status == 200) {
          var response = JSON.parse(xhr.responseText);
          
          var attributes = {
            url: response['fileUrl'],
            href: response['fileUrl']
          }
          console.log(attributes);
          successCallback(attributes)
        }
      })
  
      xhr.send(formData)
    }
  
    function createStorageKey(file) {
      var date = new Date()
      var day = date.toISOString().slice(0,10)
      var name = date.getTime() + "-" + file.name
      return [ "tmp", day, name ].join("/")
    }
  
    function createFormData(key, file) {
      var data = new FormData()
      data.append("csrfmiddlewaretoken", getCookie('csrftoken'));
      data.append("key", key)
      data.append("Content-Type", file.type)
      data.append("file", file)
      return data
    }
  })();

  /* Disable submit button once clicked to prevent accidental double submission */
  $(document).ready(function(){
    $("form").submit(function(e) {
      $(e.target).find('button[type="submit"').attr('disabled', true);
      $(e.target).find('input[type="submit"').attr('disabled', true);
      return true;
    });
  });

  $(document).ready(function(){
    $('a[data-action="reply-to-comment"]').click(function(e) {
      e.preventDefault();
      var anchor = $(e.target);
      var parentCommentId = anchor.data("comment-id");
      var template = $("#reply-template").html();
      var html = template.replace(new RegExp("<<commentid>>"), parentCommentId)
      
      var commentContainer = $('div[data-container="subcomments-' + parentCommentId + '"]').first();
      commentContainer.append(html);
      commentContainer.find('button[data-action="cancel-reply"]').click(function(e) {
        var replyButton = $(e.target);
        var replyFormContainer = replyButton.parents('div[data-container="reply-form"]').first();
        replyFormContainer.remove();
      });
      anchor.remove();
      return true;
    });
  });

/*
 * Logic to detect if a user has read a post
 * 
 * The logic is simple - a post is considered read if the entire div is visible in the browser.
 * The div for a post also contains the comments in the post
 * 
 * - We use a code snippet to detect if the div is in the viewport. See isElementInViewport
 * - We call the isElementInViewport function every time there is a scroll event or the browser is resized
 * - If the visibility of a post changes from previously invisible to visible, we mark the post as read
 * 
 * Now, if a post is read, and all it's child comments have also been read, we don't do any of these checks
 * 
 * To notify the server, we update the lastSeenTime for the post. The lastSeenTime is the time on the server
 * when the page was loaded. So if the page loaded at 10:00 AM, and I read the posts and it's comments at 10:15 AM,
 * the API call to the server will indicate the post was lastSeenAt 10:00 AM. 
 * This way, posts and comments created between 10:00 AM and 10:15 AM will still show as unread
 * 
 * We can revisit this strategy if we actively poll the server for new changes, but that isn't on the roadmap for now at least.
 */

/*
* Code to detect if a user has read a post
* CREDIT: https://stackoverflow.com/a/7557433/242940
*/
function isElementInViewport (el) {
  // Special bonus for those using jQuery
  if (typeof jQuery === "function" && el instanceof jQuery) {
      el = el[0];
  }
  var rect = el.getBoundingClientRect();
  return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) && /* or $(window).height() */
      rect.right <= (window.innerWidth || document.documentElement.clientWidth) /* or $(window).width() */
  );
}

function onceUserHasReadPost(callback) {
  var visibilityOfPost = {};
  $("div.post.unread, div.post.has-unread-children").each(function(index, el){
    var postId = el.id;
    visibilityOfPost[postId] = false;
  });
  return function () {
    $("div.post.unread, div.post.has-unread-children").each(function(index, el) {
      var postId = el.id;
      var oldVisible = visibilityOfPost[postId];
      if (oldVisible) {
        return;
      }
      var visible = isElementInViewport(el);
      if (visible) {
        visibilityOfPost[postId] = true;
        callback(postId);
      }
    });
  }
}

// Add scroll handler only if we are on the posts page
$(window).on('DOMContentLoaded', function(){
  if ($("div.post-details").length > 0) {
    var csrftoken = getCookie('csrftoken');
    var userReadPostHandler = onceUserHasReadPost(function(postId) {
      var postIdInt = postId.split("-")[1]
      var url = "/api/posts/" + postIdInt + "/lastseenat/";

      // serverTimeISO is a global variable created on page load in post.html
      $.post(url, {'csrfmiddlewaretoken': csrftoken, "last_seen": serverTimeISO });
    });

    /* Call our handler immediately the first time round */
    userReadPostHandler();

    /* And then set a callback on dom events */
    $(window).on('load resize scroll', userReadPostHandler);
  }
});

/* END logic to detect if a post is read */
